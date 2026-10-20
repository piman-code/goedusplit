"""Folder-scoped preparation choices; never stores scores or analysis results."""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path


def identity(group):
    folder=group.get('input_folder') or os.path.commonpath([str(Path(p).resolve().parent) for p in group['response']])
    return {'folder':str(Path(folder).resolve()),'round':list(group['key'])}


def settings_key(group):
    encoded=json.dumps(identity(group),ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return 'analysis_preparation/v1/'+hashlib.sha256(encoded.encode()).hexdigest()


def save_choices(settings,group,choices):
    # Explicit allowlist prevents accidental student/result serialization.
    payload={'identity':identity(group),'files':{k:str(choices.get(k,'') or '') for k in ('iteminfo','cuts','grade5_report')},
             'perform':[str(p) for p in choices['perform']], 'pencil_weight':float(choices['pencil_weight']),
             'file_weights':bool(choices['file_weights']),'include':bool(choices['include']),
             'manual_cut_scores':{level:float(choices['manual_cut_scores'][level]) for level in 'ABCDE'}}
    settings.setValue(settings_key(group),json.dumps(payload,ensure_ascii=False))
    settings.sync()
    return int(settings.status().value)==0


def load_choices(settings,group):
    raw=settings.value(settings_key(group),'')
    if not raw:return None
    try:
        data=json.loads(raw)
        if data['identity']!=identity(group):return None
        if set(data['files'])!={'iteminfo','cuts','grade5_report'}:return None
        if not all(isinstance(v,str) for v in data['files'].values()):return None
        if not isinstance(data['perform'],list) or not all(isinstance(v,str) for v in data['perform']):return None
        if not all(type(data[k]) is bool for k in ('file_weights','include')):return None
        weight=data['pencil_weight']
        if isinstance(weight,bool) or not isinstance(weight,(int,float)) or not math.isfinite(weight) or not 0<=weight<=100:return None
        cuts=data.get('manual_cut_scores')
        if cuts is not None:
            if not isinstance(cuts,dict) or set(cuts)!=set('ABCDE'):return None
            if not all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=100 for v in cuts.values()):return None
        missing=[]
        for category,path in data['files'].items():
            if path and not Path(path).is_file():missing.append(category);data['files'][category]=''
        kept=[]
        for path in data['perform']:
            if Path(path).is_file():kept.append(path)
            else:missing.append('perform')
        data['perform']=kept;data['missing']=missing
        return data
    except (ValueError,TypeError,KeyError):return None
