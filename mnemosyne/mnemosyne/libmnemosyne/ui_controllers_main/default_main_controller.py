#
# default_main_controller.py <Peter.Bienstman@UGent.be>
#

import os
import copy
import time

from mnemosyne.libmnemosyne.translator import _
from mnemosyne.libmnemosyne.fact import Fact
from mnemosyne.libmnemosyne.utils import expand_path, contract_path
from mnemosyne.libmnemosyne.ui_controller_main import UiControllerMain


class DefaultMainController(UiControllerMain):

    def heartbeat(self):

        """To be called once a day, to make sure that the logs get uploaded
        even if the user leaves the program open for a very long time.

        """
        
        self.log().dump_to_txt_log()
        self.log().deactivate()
        self.log().activate()   
        
    def update_title(self):
        database_name = os.path.basename(self.config()["path"]).\
            split(self.database().suffix)[0]
        title = _("Mnemosyne")
        if database_name != _("default"):
            title += " - " + database_name
        self.main_widget().set_window_title(title)

    def add_cards(self):
        self.stopwatch().pause()
        self.main_widget().run_add_cards_dialog()
        review_controller = self.ui_controller_review()
        review_controller.reload_counters()
        if review_controller.card is None:
            review_controller.new_question()
        else:
            self.review_widget().update_status_bar()
        self.stopwatch().unpause()

    def edit_current_card(self):
        self.stopwatch().pause()
        review_controller = self.ui_controller_review()
        self.main_widget().run_edit_fact_dialog(review_controller.card.fact)
        review_controller.reload_counters()
        if review_controller.card is None:
            self.review_widget().update_status_bar()
            review_controller.new_question()         
        review_controller.update_dialog(redraw_all=True)
        self.stopwatch().unpause()

    def create_new_cards(self, fact_data, card_type, grade, tag_names,
                         warn=True):

        """Create a new set of related cards. If the grade is 2 or higher,
        we perform a initial review with that grade and move the cards into
        the long term retention process. For other grades, we treat the card
        as still unseen and keep its grade at -1. This puts the card on equal
        footing with ungraded cards created during the import process. These
        ungraded cards are pulled in at the end of the review process, either
        in the order they were added, on in random order.

        """

        db = self.database()
        if db.has_fact_with_data(fact_data, card_type):
            if warn:
                self.main_widget().information_box(\
              _("Card is already in database.\nDuplicate not added."))
            return
        fact = Fact(fact_data, card_type)
        tags = set()
        for tag_name in tag_names:
            tags.add(db.get_or_create_tag_with_name(tag_name))
        duplicates = db.duplicates_for_fact(fact)
        if warn and len(duplicates) != 0:
            answer = self.main_widget().question_box(\
              _("There is already data present for:\n\N") +
              "".join(fact[k] for k in card_type.required_fields()),
              _("&Merge and edit"), _("&Add as is"), _("&Do not add"))
            if answer == 0: # Merge and edit.
                db.add_fact(fact)
                for card in card_type.create_related_cards(fact):
                    if grade >= 2:
                        self.scheduler().set_initial_grade(card, grade)
                    db.add_card(card)  
                merged_fact_data = copy.copy(fact.data)
                for duplicate in duplicates:
                    for key in fact_data:
                        if key not in card_type.required_fields():
                            merged_fact_data[key] += " / " + duplicate[key]
                    db.delete_fact_and_related_data(duplicate)
                fact.data = merged_fact_data              
                self.main_widget().run_edit_fact_dialog(fact, allow_cancel=False)
                return
            if answer == 2: # Don't add.
                return
        db.add_fact(fact)
        cards = []
        for card in card_type.create_related_cards(fact):
            self.log().added_card(card)
            if grade >= 2:
                self.scheduler().set_initial_grade(card, grade)
            card.tags = tags
            db.add_card(card)
            cards.append(card)
        db.save()
        if self.ui_controller_review().learning_ahead == True:
            self.ui_controller_review().reset()
        return cards # For testability.

    def update_related_cards(self, fact, new_fact_data, new_card_type, \
                             new_tag_names, correspondence, warn=True):
        # Change card type.
        db = self.database()
        old_card_type = fact.card_type       
        if old_card_type != new_card_type:
            old_card_type_id_uncloned = old_card_type.id.split("_CLONED", 1)[0]
            new_card_type_id_uncloned = new_card_type.id.split("_CLONED", 1)[0] 
            converter = self.component_manager.get_current\
                  ("card_type_converter", used_for=(old_card_type.__class__,
                                                    new_card_type.__class__))
            if old_card_type_id_uncloned == new_card_type_id_uncloned:
                fact.card_type = new_card_type
                updated_cards = db.cards_from_fact(fact)      
            elif not converter:
                if warn:
                    answer = self.main_widget().question_box(\
          _("Can't preserve history when converting between these card types.")\
                  + " " + _("The learning history of the cards will be reset."),
                  _("&OK"), _("&Cancel"), "")
                else:
                    answer = 0
                if answer == 1: # Cancel.
                    return -1
                else:
                    db.delete_fact_and_related_data(fact)
                    self.create_new_cards(new_fact_data, new_card_type,
                                          grade=-1, cat_names=new_cat_names)
                    return 0
            else:
                # Make sure the converter operates on card objects which
                # already know their new type, otherwise we could get
                # conflicting ids.
                fact.card_type = new_card_type
                cards_to_be_updated = db.cards_from_fact(fact)
                for card in cards_to_be_updated:
                    card.fact = fact
                # Do the conversion.
                new_cards, updated_cards, deleted_cards = \
                   converter.convert(cards_to_be_updated, old_card_type,
                                     new_card_type, correspondence)
                if len(deleted_cards) != 0:
                    if warn:
                        answer = self.main_widget().question_box(\
          _("This will delete cards and their history.") + " " +\
          _("Are you sure you want to do this,") + " " +\
          _("and not just deactivate cards in the 'Activate cards' dialog?"),
                      _("&Proceed and delete"), _("&Cancel"), "")
                    else:
                        answer = 0
                    if answer == 1: # Cancel.
                        return -1
                for card in deleted_cards:
                    db.delete_card(card)
                for card in new_cards:
                    db.add_card(card)
                for card in updated_cards:
                    db.update_card(card)
                if new_cards and self.ui_controller_review().learning_ahead:
                    self.ui_controller_review().reset()
                    
        # Update facts and cards.
        new_cards, updated_cards, deleted_cards = \
            fact.card_type.update_related_cards(fact, new_fact_data)
        fact.modification_time = time.time()
        fact.data = new_fact_data
        db.update_fact(fact)
        for card in deleted_cards:
            db.delete_card(card)
        for card in new_cards:
            db.add_card(card)
        for card in updated_cards:
            db.update_card(card)
        if new_cards and self.ui_controller_review().learning_ahead == True:
            self.ui_controller_review().reset()
            
        # Update categories.
        old_tags = set()
        tags = set()
        for tag_name in new_tag_names:
            tags.add(db.get_or_create_tag_with_name(tag_name))
        for card in self.database().cards_from_fact(fact):
            old_tags = old_tags.union(card.tags)
            card.tags = tags
            db.update_card(card)
        for tag in old_tags:
            db.remove_tag_if_unused(tag)
        db.save()

        # Update card present in UI.
        review_controller = self.ui_controller_review()
        if review_controller.card:
            review_controller.card = \
                self.database().get_card(review_controller.card._id)
            review_controller.update_dialog(redraw_all=True)
        return 0

    def delete_current_fact(self):
        self.stopwatch().pause()
        db = self.database()
        review_controller = self.ui_controller_review()
        fact = review_controller.card.fact
        no_of_cards = len(db.cards_from_fact(fact))
        if no_of_cards == 1:
            question = _("Delete this card?")
        elif no_of_cards == 2:
            question = _("Delete this card and 1 related card?") + " "  +\
                      _("Are you sure you want to do this,") + " " +\
          _("and not just deactivate cards in the 'Activate cards' dialog?")
        else:
            question = _("Delete this card and") + " " + str(no_of_cards - 1) \
                       + " " + _("related cards?") + " " +\
                       _("Are you sure you want to do this,") + " " +\
          _("and not just deactivate cards in the 'Activate cards' dialog?")
        answer = self.main_widget().question_box(question, _("&Delete"),
                                          _("&Cancel"), "")
        if answer == 1: # Cancel.
            return
        db.delete_fact_and_related_data(fact)
        db.save()
        review_controller.reload_counters()
        review_controller.rebuild_queue()
        review_controller.new_question()
        self.review_widget().update_status_bar()
        review_controller.update_dialog(redraw_all=True)
        self.stopwatch().unpause()

    def file_new(self):
        self.stopwatch().pause()
        db = self.database()
        suffix = db.suffix
        out = self.main_widget().save_file_dialog(path=self.config().basedir,
                            filter=_("Mnemosyne databases (*%s)" % suffix),
                            caption=_("New"))
        if not out:
            self.stopwatch().unpause()
            return
        if not out.endswith(suffix):
            out += suffix
        db.unload()
        db.new(out)
        db.load(self.config()["path"])
        self.log().loaded_database()
        self.ui_controller_review().reset()
        self.ui_controller_review().update_dialog()
        self.update_title()
        self.stopwatch().unpause()

    def file_open(self):
        self.stopwatch().pause()
        old_path = expand_path(self.config()["path"], self.config().basedir)
        out = self.main_widget().open_file_dialog(path=old_path,
            filter=_("Mnemosyne databases (*%s)" % self.database().suffix))
        if not out:
            self.stopwatch().unpause()
            return
        try:
            self.database().unload()
            self.log().saved_database()
        except RuntimeError, error:
            self.main_widget().error_box(str(error))
            self.stopwatch().unpause()
            return            
        self.ui_controller_review().reset()
        try:
            self.database().load(out)
            self.log().loaded_database()
        except MnemosyneError, e:
            self.main_widget().show_exception(e)
            self.stopwatch().unpause()
            return
        self.ui_controller_review().new_question()
        self.update_title()
        self.stopwatch().unpause()

    def file_save(self):
        self.stopwatch().pause()
        try:
            self.database().save()
            self.log().saved_database()
        except RuntimeError, error:
            self.main_widget().error_box(str(error))
        self.stopwatch().unpause()

    def file_save_as(self):
        self.stopwatch().pause()
        suffix = self.database().suffix
        old_path = expand_path(self.config()["path"], self.config().basedir)
        out = self.main_widget().save_file_dialog(path=old_path,
            filter=_("Mnemosyne databases (*%s)" % suffix))
        if not out:
            self.stopwatch().unpause()
            return
        if not out.endswith(suffix):
            out += suffix
        try:
            self.database().save(out)
            self.log().saved_database()
        except RuntimeError, error:
            self.main_widget().error_box(str(error))
            self.stopwatch().unpause()
            return
        self.ui_controller_review().update_dialog()
        self.update_title()
        self.stopwatch().unpause()

    def insert_img(self):
        fname = self.parent().ui_controller_main().insert_img()
        if fname:
            self.insertPlainText("<img src=\"" + fname + "\">")
        
            
        config = self.parent().config()
        path = expand_path(config["import_img_dir"], config.basedir)
        fname = unicode(QFileDialog.getOpenFileName(self, _("Insert image"),
                        path, _("Image files") + \
                        " (*.png *.gif *.jpg *.bmp *.jpeg" + \
                        " *.PNG *.GIF *.jpg *.BMP *.JPEG)"))
        if fname:
            self.insertPlainText("<img src=\"" + \
                contract_path(fname, config.basedir) + "\">")
            config["import_img_dir"] = contract_path(os.path.dirname(fname),
                config.basedir)
            
    def insert_img(self, filter):

        """Show a file dialog filtered on the supported filetypes, get a
        filename, massage it, and return it to the widget to be inserted.
        There is more media file logic inside the database code too, as the
        user could also just type in the html tags as opposed to passing
        through the fileselector here.

        """

        from mnemosyne.libmnemosyne.utils import copy_file_to_dir

        basedir, mediadir = self.config().basedir, self.config().mediadir()
        path = expand_path(self.config()["import_img_dir"], basedir)
        filter = _("Image files") + " " + filter
        fname = self.main_widget().open_file_dialog(\
            path, filter, _("Insert image"))
        if not fname:
            return ""
        else:
            self.config()["import_img_dir"] = contract_path(\
                os.path.dirname(fname), basedir)
            fname = copy_file_to_dir(fname, mediadir)
            return contract_path(fname, mediadir)
        
    def insert_sound(self, filter):

        from mnemosyne.libmnemosyne.utils import copy_file_to_dir

        basedir, mediadir = self.config().basedir, self.config().mediadir()
        path = expand_path(self.config()["import_sound_dir"], basedir)
        filter = _("Sound files") + " " + filter
        fname = self.main_widget().open_file_dialog(\
            path, filter, _("Insert sound"))
        if not fname:
            return ""
        else:
            self.config()["import_sound_dir"] = contract_path(\
                os.path.dirname(fname), basedir)
            fname = copy_file_to_dir(fname, mediadir)
            return contract_path(fname, mediadir)

    def card_appearance(self):
        self.stopwatch().pause()
        self.main_widget().run_card_appearance_dialog()
        self.ui_controller_review().update_dialog(redraw_all=True)
        self.stopwatch().unpause()
        
    def activate_plugins(self):
        self.stopwatch().pause()
        self.main_widget().run_activate_plugins_dialog()
        self.ui_controller_review().update_dialog(redraw_all=True)
        self.stopwatch().unpause()

    def manage_card_types(self):
        self.stopwatch().pause()
        self.main_widget().run_manage_card_types_dialog()
        self.stopwatch().unpause()
        
    def edit_deck(self):
        self.stopwatch().pause()
        self.main_widget().run_edit_deck_dialog()
        self.stopwatch().unpause()
        
    def configure(self):
        self.stopwatch().pause()
        self.main_widget().run_configuration_dialog()
        self.stopwatch().unpause()

    def show_statistics(self):
        stopwatch.pause()
        self.widget.run_show_statistics_dialog()
        stopwatch.unpause()

