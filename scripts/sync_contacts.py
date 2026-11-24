import os
from email.utils import getaddresses, parsedate_to_datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/spreadsheets']
HEADERS = ['Name','Email','Organization','Role','Research interests','Source','First contact','Last contact','Status','Follow-up date','Notes','Gmail thread']
LABEL = 'OCRI/Research Contacts'
def main():
    required = ['GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REFRESH_TOKEN','OCRI_SHEET_ID']
    if any(not os.getenv(k) for k in required):
        raise SystemExit('Required GitHub Actions secrets are missing.')
    creds = Credentials(None, refresh_token=os.environ['GOOGLE_REFRESH_TOKEN'], token_uri='https://oauth2.googleapis.com/token', client_id=os.environ['GOOGLE_CLIENT_ID'], client_secret=os.environ['GOOGLE_CLIENT_SECRET'], scopes=SCOPES)
    gmail = build('gmail','v1',credentials=creds,cache_discovery=False)
    sheets = build('sheets','v4',credentials=creds,cache_discovery=False).spreadsheets()
    sid = os.environ['OCRI_SHEET_ID']
    own = gmail.users().getProfile(userId='me').execute()['emailAddress'].lower()
    labels = gmail.users().labels().list(userId='me').execute()['labels']
    lid = next((x['id'] for x in labels if x['name']==LABEL), None)
    if not lid:
        lid = gmail.users().labels().create(userId='me',body={'name':LABEL}).execute()['id']
    meta = sheets.get(spreadsheetId=sid,fields='sheets(properties(title,sheetId))').execute()
    tab = next((x['properties'] for x in meta['sheets'] if x['properties']['title']=='Contacts'),None)
    if tab is None:
        sheets.batchUpdate(spreadsheetId=sid,body={'requests':[{'addSheet':{'properties':{'title':'Contacts','gridProperties':{'frozenRowCount':1}}}}]}).execute()
    values = sheets.values()
    rows = values.get(spreadsheetId=sid,range='Contacts!A:L').execute().get('values',[])
    if rows and rows[0]!=HEADERS:
        raise SystemExit('Unexpected contact sheet headers; no data changed.')
    records = {}
    for i,row in enumerate(rows[1:],2):
        row = (row+['']*12)[:12]
        key = row[1].strip().lower()
        if not key: continue
        if key in records:
            raise SystemExit('Existing duplicate emails require manual reconciliation; no rows changed.')
        records[key]=(i,row)
    changes={}
    seen=set()
    for query in ['subject:OCRI -in:spam -in:trash','label:"OCRI/Research Contacts" -in:spam -in:trash']:
        token=None
        while True:
            result=gmail.users().threads().list(userId='me',q=query,pageToken=token).execute()
            for item in result.get('threads',[]):
                tid=item['id']
                if tid in seen: continue
                seen.add(tid)
                thread=gmail.users().threads().get(userId='me',id=tid,format='metadata',metadataHeaders=['From','To','Date','Subject','Auto-Submitted']).execute()
                for msg in thread['messages']:
                    if set(msg.get('labelIds',[])) & {'SPAM','TRASH','DRAFT'}: continue
                    h={x['name'].lower():x['value'] for x in msg['payload'].get('headers',[])}
                    senders=getaddresses([h.get('from','')])
                    outgoing=any(a.lower()==own for _,a in senders)
                    people=getaddresses([h.get('to','')]) if outgoing else senders
                    date=parsedate_to_datetime(h['date']).date().isoformat() if h.get('date') else ''
                    auto=h.get('auto-submitted','no').lower()!='no' or h.get('subject','').lower().startswith(('automatic reply','auto reply','thanks for writing'))
                    for name,email in people:
                        key=email.strip().lower()
                        if not key or key==own or key.startswith(('mailer-daemon@','postmaster@','no-reply@','noreply@')): continue
                        idx,row=records.get(key,(None,['']*12))
                        row[0]=row[0] or name
                        row[1]=key
                        row[5]=row[5] or ('Direct outreach' if outgoing else 'Website / research inquiry')
                        if date:
                            row[6]=min(filter(None,[row[6],date]))
                            row[7]=max(row[7],date)
                        if row[8] in ('','New','Contacted','Automated acknowledgment'):
                            row[8]='Contacted' if outgoing and not row[8] else ('Automated acknowledgment' if auto and not outgoing else ('Responded' if not outgoing else row[8]))
                        row[11]='https://mail.google.com/mail/u/0/#all/'+tid
                        records[key]=(idx,row)
                        changes[key]=(idx,row)
                    if lid not in msg.get('labelIds',[]):
                        gmail.users().messages().modify(userId='me',id=msg['id'],body={'addLabelIds':[lid]}).execute()
            token=result.get('nextPageToken')
            if not token: break
    if not rows:
        values.update(spreadsheetId=sid,range='Contacts!A1:L1',valueInputOption='RAW',body={'values':[HEADERS]}).execute()
    updates=[{'range':f'Contacts!A{i}:L{i}','values':[r]} for i,r in changes.values() if i is not None]
    if updates: values.batchUpdate(spreadsheetId=sid,body={'valueInputOption':'RAW','data':updates}).execute()
    new=[r for i,r in changes.values() if i is None]
    if new: values.append(spreadsheetId=sid,range='Contacts!A:L',valueInputOption='RAW',insertDataOption='INSERT_ROWS',body={'values':new}).execute()
    print('Contact synchronization completed.')
if __name__=='__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Synchronization failed; check API permissions, credentials and sheet configuration.')
