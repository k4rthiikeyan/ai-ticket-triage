"""Record schema version and a non-disclosing digest of persistent owner content."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--compare',type=Path)
    args=parser.parse_args()
    raw=os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
    url=make_url(raw)
    if not url.host or not url.host.endswith('.neon.tech'):
        raise SystemExit('Expected the explicitly linked Neon database; no query was made.')
    url=url.set(drivername='postgresql+psycopg',host=url.host.replace('-pooler.','.'))
    engine=create_engine(url,connect_args={'connect_timeout':10,'prepare_threshold':None})
    with engine.connect() as db:
        version=db.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        stable={}
        stable['ticket']=[tuple(r) for r in db.execute(text('SELECT id, subject, body, revision, status, category_id, priority, queue_id, created_at, updated_at FROM ticket WHERE workspace_id=1 ORDER BY id'))]
        stable['article']=[tuple(r) for r in db.execute(text('SELECT id, title, body, revision, is_policy, active, updated_at FROM article WHERE workspace_id=1 ORDER BY id'))]
        for table,fields in [('decision','id,ticket_id,action,note'),('recommendationrun','id,ticket_id,payload'),('note','id,ticket_id,body'),('ticketrevision','id,ticket_id,revision,subject,body')]:
            stable[table]=[tuple(r) for r in db.execute(text(f'SELECT {fields} FROM {table} WHERE ticket_id IN (SELECT id FROM ticket WHERE workspace_id=1) ORDER BY id'))]
        digest=hashlib.sha256(json.dumps(stable,default=str,sort_keys=True).encode()).hexdigest()
        columns={c['name'] for c in inspect(db).get_columns('ticket')}
        report={'schema_version':version,'owner_digest':digest,'owner_counts':{t:len(rows) for t,rows in stable.items()},
                'resolution_columns_present':{'customer_id','resolution_state','outcome_version','answer','draft_run_id'}<=columns}
        if args.compare:
            prior=json.loads(args.compare.read_text(encoding='utf-8'))
            report['owner_content_preserved']=prior['owner_digest']==digest
            assert report['owner_content_preserved'],'Persistent owner content changed; inspect before accepting the release.'
    engine.dispose()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
