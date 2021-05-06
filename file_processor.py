import pandas as pd
import streamlit as st
import base64
from datetime import datetime
import math


st.set_page_config(page_title='Keeps File Processor',layout='wide')
st.header('Keeps File Processor')
st.subheader('File Upload')
st.write('Upload the following four files (Leads, Purchases, Keeps Daily Budget, UTM Bridge File) using the widgets below.')
st.write('The output will be a file which can be downloaded and used to update the Keeps Tableau dashboard.')
st.write('')
st.write('')


## FUNCTIONS
# Function to eliminate unnecessary rows after joining the budget to the lead, order, and chartable data sources
def reduce_df(df):
    
    crit_1 = df['Actual Drop Day'] < datetime.date(2021,5,3) #datetime.today().date()
    crit_2 = (df['event_date'] >= df['Actual Drop Day']) & (df['event_date'] < df['next_drop_date'])
    crit_3 = (df['Actual Drop Day'] == df['next_drop_date']) & (df['event_date'] >= df['Actual Drop Day'])
    
    reduced_df = df[crit_1 & (crit_2 | crit_3)]
    
    return reduced_df


# Function to rebuild the budget with the Actual Drop Day and Next Drop Day columns
def rebuild_budget(daily_budget_df):

    rebuilt_budget_df = pd.DataFrame()

    for show in daily_budget_df['Show Name'].unique():
        temp_list = []
        temp_df = daily_budget_df[daily_budget_df['Show Name'] == show]
        drop_series = temp_df['Actual Drop Day'].reset_index()

        shifted_drop_series = drop_series.shift(-1)
        index_list = shifted_drop_series.index.values

        for item in index_list:
            if math.isnan(shifted_drop_series['index'][item]):
                temp_list.append(drop_series['Actual Drop Day'][item])
            else:
                temp_list.append(shifted_drop_series['Actual Drop Day'][item])

        temp_df.reset_index(inplace=True)
        temp_df['next_drop_date'] = pd.Series(temp_list)
        temp_df.drop(['index'],axis=1)

        rebuilt_budget_df = pd.concat([rebuilt_budget_df,temp_df],axis=0)

    return rebuilt_budget_df


# Construct user interface
col1, col2 = st.beta_columns(2)

with col1:
    uploaded_purchases = st.file_uploader(label='Purchases',accept_multiple_files=False)

with col2:
    uploaded_leads = st.file_uploader(label='Leads',accept_multiple_files=False)

uploaded_daily_budget = st.file_uploader(label='Keeps Budget',accept_multiple_files=False)
uploaded_chartable_data = st.file_uploader(label='Chartable Data',accept_multiple_files=False)


### Create CPO and CPL Extract ###
if (uploaded_leads is not None) and (uploaded_daily_budget is not None) and (uploaded_purchases is not None):

    # Create DataFrames from uploaded CSV files
    looker_file_purchases_df = pd.read_csv(uploaded_purchases,parse_dates=["User's First Non-refunded Purchase Date","Lead Created Date"])
    looker_file_leads_df = pd.read_csv(uploaded_leads,parse_dates=['Lead Created Date'])
    daily_budget_df = pd.read_csv(uploaded_daily_budget,parse_dates=['Broadcast Week','Actual Drop Day'])
    daily_budget_df = daily_budget_df.sort_values(by=['Show Name','Actual Drop Day'])


    # Drop unused columns
    looker_file_purchases_df.drop(labels=['Unnamed: 0','User ID','Lead Created Date','Utm Source'],axis=1,inplace=True)
    looker_file_leads_df.drop(labels=['Unnamed: 0','User ID','Utm Source'],axis=1,inplace=True)


    # Create purchase and lead indicator column
    looker_file_purchases_df['orders'] = 1
    looker_file_leads_df['leads'] = 1


    # Aggregate purchase and lead data by date and show name
    looker_purchases_agg_df = looker_file_purchases_df.groupby(["User's First Non-refunded Purchase Date",'Utm Campaign']).sum()['orders'].reset_index()
    looker_leads_agg_df = looker_file_leads_df.groupby(['Lead Created Date','Utm Campaign']).sum()['leads'].reset_index()


    # Create columns for percent of show's audience that is male and female
    daily_budget_df['Percent Male'] = daily_budget_df['% M/F'].apply(lambda x: int(x.split('/')[0].strip('M'))/100)
    daily_budget_df['Percent Female'] = daily_budget_df['% M/F'].apply(lambda x: int(x.split('/')[1].strip('F'))/100)


    # Rebuild budget
    rebuilt_budget_df = rebuild_budget(daily_budget_df)


    # Create final DataFrames to export for Tableau data sources
    purchases_df = pd.merge(rebuilt_budget_df,looker_purchases_agg_df,left_on=['UTM'],right_on=['Utm Campaign'],how='left')
    leads_df = pd.merge(rebuilt_budget_df,looker_leads_agg_df,left_on=['UTM'],right_on=['Utm Campaign'],how='left')


    # Change date column name to event_date
    purchases_df.rename({"User's First Non-refunded Purchase Date":'event_date'}, axis=1)
    leads_df.rename({'Lead Created Date':'event_date'})


    # Create final leads and purchases DataFrames by eliminating negative date_diffs and including drops which had 0 leads or orders
    final_purchases_df = reduce_df(purchases_df)
    final_purchases_df.fillna(value={'orders':0},inplace=True)

    final_leads_df = reduce_df(leads_df)
    final_leads_df.fillna(value={'leads':0},inplace=True)

    
    st.write('')
    st.write('')



else:
    st.write('Please upload all the files to successfully output your lead and order files')



### Create Chartable Extract ###
if (uploaded_leads is not None) and (uploaded_daily_budget is not None) and (uploaded_purchases is not None) and (uploaded_chartable_data is not None):

    ## Chartable Processing ##
    chartable_df = pd.read_csv(uploaded_chartable_data, parse_dates=['event_timestamp'], skiprows=1, skipfooter=1)

    chartable_df['show_name'] = chartable_df['ad_campaign_name'].apply(lambda x: x.split(' - ')[0])
    chartable_df['event_date'] = chartable_df['event_timestamp'].apply(lambda x: x.date())

    chartable_df = chartable_df[(chartable_df['event_type'] == 'lead') | (chartable_df['event_type'] == 'purchase')].groupby(['event_date','show_name','event_type']).count()['event_id'].reset_index()
    chartable_df.rename({'event_id':'count'},axis=1,inplace=True)
    chartable_df['source'] = 'Chartable'


    ## Looker Processing ##
    # Leads

    leads_df = pd.read_csv(uploaded_leads,parse_dates=['Lead Created Date'])
    leads_df['Lead Created Date'] = leads_df['Lead Created Date'].apply(lambda x: x.date())

    leads_df['event_type'] = 'lead'
    looker_leads_df = leads_df.groupby(['Lead Created Date','Utm Campaign','event_type']).count()['Utm Source'].reset_index()
    looker_leads_df.rename({'Utm Source': 'count', 'Lead Created Date': 'event_date','Utm Campaign':'show_name'}, axis=1, inplace=True)
    looker_leads_df['source'] = 'Looker'

    # Purchases
    purchases_df = pd.read_csv(uploaded_purchases,parse_dates=["User's First Non-refunded Purchase Date"])
    purchases_df["User's First Non-refunded Purchase Date"] = purchases_df['User\'s First Non-refunded Purchase Date'].apply(lambda x: x.date())

    purchases_df['event_type'] = 'purchase'
    looker_purchases_df = purchases_df.groupby(["User's First Non-refunded Purchase Date",'Utm Campaign','event_type']).count()['Utm Source'].reset_index()
    looker_purchases_df.rename({'Utm Source':'count',"User's First Non-refunded Purchase Date": 'event_date','Utm Campaign':'show_name'}, axis=1, inplace=True)
    looker_purchases_df['source'] = 'Looker'

    # Concatenate Together
    looker_all_df = pd.concat([looker_leads_df,looker_purchases_df])


    ## Daily Budget Processing ##
    daily_budget_df = pd.read_csv(uploaded_daily_budget, parse_dates=['Actual Drop Day'])
    daily_budget_df['Actual Drop Day'] = daily_budget_df['Actual Drop Day'].apply(lambda x: x.date())

    # Rebuild budget
    rebuilt_budget_df = rebuild_budget(daily_budget_df)


    ## Creation of final files ##
    chartable_final_df = pd.merge(rebuilt_budget_df, chartable_df, left_on=['Show Name'], right_on=['show_name'], how='left')
    chartable_final_df = chartable_final_df[~chartable_final_df['count'].isnull()]
    
    looker_final_df = pd.merge(rebuilt_budget_df,looker_all_df, left_on=['UTM'], right_on=['show_name'], how='left')


    ## Reduce rows and group records ##
    chartable_final_df = reduce_df(chartable_final_df)
    chartable_final_grp_df = chartable_final_df.groupby(['source','Show Name','Actual Drop Day','next_drop_date','event_type']).sum()['count'].reset_index()

    
    looker_final_df = reduce_df(looker_final_df)
    looker_final_df = looker_final_df[looker_final_df['Show Name'].isin(chartable_final_df['Show Name'].unique())]
    looker_final_grp_df = looker_final_df.groupby(['source','Show Name','Actual Drop Day','next_drop_date','event_type']).sum()['count'].reset_index()


    ## Produce final data frame ##
    final_df = pd.concat([chartable_final_grp_df, looker_final_grp_df]).reset_index()

    st.write('')
    st.write('')

else:
    st.write('Please upload all the files to successfully output your lead and order files')



### OUTPUT ###
st.subheader('Data Source Output')
st.write('')
st.write('')

# Create download link for transactions file
orders_csv = final_purchases_df.to_csv(index=False)
b64 = base64.b64encode(orders_csv.encode()).decode()  # some strings <-> bytes conversions necessary here
orders_href = f'<a href="data:file/csv;base64,{b64}">Download your Orders CSV File</a> (right-click and save as &lt;some_name&gt;.csv)'
st.markdown(orders_href, unsafe_allow_html=True)

leads_csv = final_leads_df.to_csv(index=False)
b64 = base64.b64encode(leads_csv.encode()).decode()  # some strings <-> bytes conversions necessary here
leads_href = f'<a href="data:file/csv;base64,{b64}">Download your Leads CSV File</a> (right-click and save as &lt;some_name&gt;.csv)'
st.markdown(leads_href, unsafe_allow_html=True)

chartable_csv = final_df.to_csv(index=False)
b64 = base64.b64encode(chartable_csv.encode()).decode()  # some strings <-> bytes conversions necessary here
chartable_href = f'<a href="data:file/csv;base64,{b64}">Download your Chartable CSV File</a> (right-click and save as &lt;some_name&gt;.csv)'
st.markdown(chartable_href, unsafe_allow_html=True)