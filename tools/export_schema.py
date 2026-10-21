"""Regenerate the shared, machine-readable command contract."""
import json
from pathlib import Path
from desktop.security import PROFILES

variants = []
for profile, actions in PROFILES.items():
    for action in sorted(actions):
        limits = {'dx': (-40,40),'dy':(-40,40)} if action=='move' else {'delta':(-3,3)} if action=='scroll' else {'page':(1,9999)} if action=='page' else {}
        variants.append({'type':'object','additionalProperties':False,'required':['type','seq','profile','action','args'],'properties':{
            'type':{'const':'command'},'seq':{'type':'integer','minimum':1,'maximum':9007199254740991},'profile':{'const':profile},'action':{'const':action},
            'args':{'type':'object','additionalProperties':False,'required':list(limits),'properties':{k:{'type':'integer','minimum':v[0],'maximum':v[1]} for k,v in limits.items()}}
        }})
Path('shared/command.schema.json').write_text(json.dumps({'$schema':'https://json-schema.org/draft/2020-12/schema','title':'Classroom Remote Controller command v1','oneOf':variants},indent=2)+'\n',encoding='utf-8')
