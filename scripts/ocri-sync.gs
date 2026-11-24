const HEADERS=['Name','Email','Organization','Role','Research interests','Source','First contact','Last contact','Status','Follow-up date','Notes','Gmail thread'];
function installOCRI(){
  const ss=SpreadsheetApp.getActiveSpreadsheet();
  PropertiesService.getScriptProperties().setProperty('OCRI_SHEET_ID',ss.getId());
  syncOCRI();
  ScriptApp.getProjectTriggers().filter(t=>t.getHandlerFunction()==='syncOCRI').forEach(t=>ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('syncOCRI').timeBased().everyHours(1).create();
}
function syncOCRI(){
  const lock=LockService.getScriptLock(); lock.waitLock(30000);
  try {
    const ss=SpreadsheetApp.openById(PropertiesService.getScriptProperties().getProperty('OCRI_SHEET_ID'));
    const sheet=ss.getSheetByName('Contacts')||ss.insertSheet('Contacts');
    if(!sheet.getLastRow()){sheet.appendRow(HEADERS);sheet.setFrozenRows(1);}
    if(JSON.stringify(sheet.getRange(1,1,1,12).getValues()[0])!==JSON.stringify(HEADERS)) throw Error('Unexpected headers');
    const rows=sheet.getLastRow()>1?sheet.getRange(2,1,sheet.getLastRow()-1,12).getValues():[];
    const records=new Map();
    rows.forEach((r,i)=>{const k=String(r[1]).trim().toLowerCase();if(k){if(records.has(k))throw Error('Existing duplicate requires reconciliation');records.set(k,{row:r,index:i+2});}});
    const label=GmailApp.getUserLabelByName('OCRI/Research Contacts')||GmailApp.createLabel('OCRI/Research Contacts');
    const own=new Set([Session.getEffectiveUser().getEmail(),...GmailApp.getAliases()].map(x=>x.toLowerCase()));
    const seen=new Set(),changed=new Set();
    const query='{subject:OCRI label:"OCRI/Research Contacts" subject:"Patient-Initiated Research Proposal"} -in:spam -in:trash';
    for(let offset=0;;offset+=100){
      const threads=GmailApp.search(query,offset,100);
      for(const thread of threads){
        if(seen.has(thread.getId()))continue;seen.add(thread.getId());
        for(const msg of thread.getMessages()){
          if(msg.isDraft()||msg.isInTrash())continue;
          const from=addresses(msg.getFrom());const sent=from.some(p=>own.has(p.email));
          const people=sent?addresses(msg.getTo()):from;
          const date=msg.getDate();
          const auto=/^(automatic reply|auto reply|thanks for writing|out of office)/i.test(msg.getSubject())||!/^$|^no$/i.test(msg.getHeader('Auto-Submitted'));
          for(const p of people){
            if(own.has(p.email)||/^(mailer-daemon|postmaster|no-?reply)@/i.test(p.email))continue;
            const entry=records.get(p.email)||{row:Array(12).fill(''),index:0};const r=entry.row;
            r[0]=r[0]||safe(p.name);r[1]=p.email;r[5]=r[5]||(sent?'Direct outreach':'Research inquiry');
            if(!r[6]||date<new Date(r[6]))r[6]=date;
            if(!r[7]||date>=new Date(r[7])){r[7]=date;r[11]=thread.getPermalink();}
            if(!r[8])r[8]=sent?'Contacted':auto?'Automated acknowledgment':'Responded';
            else if(!sent&&!auto&&['New','Contacted','Automated acknowledgment'].includes(r[8]))r[8]='Responded';
            else if(!sent&&auto&&['New','Contacted'].includes(r[8]))r[8]='Automated acknowledgment';
            records.set(p.email,entry);changed.add(p.email);
          }
        }
        thread.addLabel(label);
      }
      if(threads.length<100)break;
    }
    const fresh=[];
    for(const k of changed){const e=records.get(k);if(e.index)sheet.getRange(e.index,1,1,12).setValues([e.row]);else fresh.push(e.row);}
    if(fresh.length)sheet.getRange(sheet.getLastRow()+1,1,fresh.length,12).setValues(fresh);
  }finally{lock.releaseLock();}
}
function safe(s){return /^[=+@-]/.test(s)?"'"+s:s;}
function addresses(s){return [...String(s).matchAll(/(?:"([^"]*)"|([^,<>]*))?\s*<([^<>\s]+@[^<>\s]+)>|([\w.!#$%&'*+/=?^_`{|}~-]+@[\w.-]+\.[a-zA-Z]{2,})/g)].map(m=>({name:(m[1]||m[2]||'').trim(),email:(m[3]||m[4]).trim().toLowerCase()}));}
