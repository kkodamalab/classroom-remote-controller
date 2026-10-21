import json
from pathlib import Path
import jsonschema
from desktop.security import PROFILES


def test_shared_schema_covers_allowlist():
    schema=json.loads(Path('shared/command.schema.json').read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    validator=jsonschema.Draft202012Validator(schema)
    assert len(schema['oneOf'])==sum(len(actions) for actions in PROFILES.values())
    for profile,actions in PROFILES.items():
        for action in actions:
            args={'dx':1,'dy':1} if action=='move' else {'delta':1} if action=='scroll' else {'page':1} if action=='page' else {}
            validator.validate({'type':'command','seq':1,'profile':profile,'action':action,'args':args})
    assert not validator.is_valid({'type':'command','seq':1,'profile':'windows','action':'shell','args':{}})
