package org.mnemosyne;
import android.app.ListActivity;
import android.content.Intent;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.ListView;

public class ActivateCardsActivity extends ListActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Bundle bundle = this.getIntent().getExtras();
        String[] values = bundle.getStringArray("saved_sets");
        String active = bundle.getString("active_set");
        ArrayAdapter<String> adapter = new ArrayAdapter<String>(this,
                android.R.layout.simple_list_item_1, values);
        setListAdapter(adapter);
        for (int position=0; position<values.length; position++)
        {
            if (((String) getListAdapter().getItem(position)).equals(active))
            {
                final ListView listView = getListView();
                listView.setChoiceMode(ListView.CHOICE_MODE_SINGLE);

                final int _position = position;
                listView.clearFocus();
                listView.post(new Runnable()
                {
                    public void run()
                    {
                        Log.d("Mnemosyne", "setting selection " + _position);
                        listView.setSelection(_position);
                        listView.setItemChecked(_position, true);
                        //listView.performItemClick(listView, _position, listView.getItemIdAtPosition(_position));
                    }
                });
                break;
            }
        }
    }

    @Override
    protected void onListItemClick(ListView l, View v, int position, long id) {
        String item = (String) getListAdapter().getItem(position);
        Intent intent = new Intent();
        intent.putExtra("saved_set", item);
        setResult(RESULT_OK, intent);
        finish();
    }
}