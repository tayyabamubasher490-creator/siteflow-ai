import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / 'buildpay_history.db'


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS check_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_no TEXT UNIQUE NOT NULL,
        project TEXT NOT NULL,
        house_type TEXT NOT NULL,
        activity TEXT NOT NULL,
        boq_items TEXT NOT NULL,
        description TEXT,
        requested_qty REAL,
        unit TEXT,
        contractor TEXT,
        consultant TEXT,
        client TEXT,
        status TEXT NOT NULL,
        documents TEXT,
        ai_review TEXT,
        human_decision TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ipcs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ipc_no TEXT UNIQUE NOT NULL,
        project TEXT NOT NULL,
        check_request_no TEXT NOT NULL,
        activity TEXT NOT NULL,
        period_from TEXT,
        period_to TEXT,
        current_qty REAL NOT NULL,
        cumulative_qty REAL NOT NULL,
        rate REAL NOT NULL,
        current_amount REAL NOT NULL,
        cumulative_amount REAL NOT NULL,
        retention REAL NOT NULL,
        net_amount REAL NOT NULL,
        documents TEXT,
        ai_review TEXT,
        human_decision TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(check_request_no) REFERENCES check_requests(request_no)
    );
    CREATE TABLE IF NOT EXISTS variations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        variation_no TEXT UNIQUE NOT NULL,
        project TEXT NOT NULL,
        check_request_no TEXT,
        boq_item TEXT NOT NULL,
        activity TEXT NOT NULL,
        original_qty REAL NOT NULL,
        previously_approved_variation REAL NOT NULL DEFAULT 0,
        approved_qty_before REAL NOT NULL DEFAULT 0,
        previously_certified_qty REAL NOT NULL DEFAULT 0,
        required_cumulative_qty REAL NOT NULL,
        proposed_additional_qty REAL NOT NULL,
        revised_proposed_qty REAL NOT NULL,
        rate REAL NOT NULL DEFAULT 0,
        estimated_value REAL NOT NULL DEFAULT 0,
        reason TEXT,
        documents TEXT,
        ai_review TEXT,
        status TEXT NOT NULL,
        human_decision TEXT,
        submitted_by TEXT,
        approver TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        details TEXT,
        created_at TEXT NOT NULL
    );
    ''')
    conn.commit()
    conn.close()


def _now():
    return datetime.now(timezone.utc).isoformat()


def next_number(prefix, table, column):
    conn = _connect()
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    n = int(row['n']) + 1
    conn.close()
    return f'{prefix}-{datetime.now().strftime("%Y%m")}-{n:04d}'


def create_check_request(data):
    now = _now()
    conn = _connect()
    conn.execute('''INSERT INTO check_requests
        (request_no,project,house_type,activity,boq_items,description,requested_qty,unit,
         contractor,consultant,client,status,documents,ai_review,human_decision,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (data['request_no'], data['project'], data['house_type'], data['activity'],
         json.dumps(data.get('boq_items', [])), data.get('description',''), data.get('requested_qty',0),
         data.get('unit',''), data.get('contractor',''), data.get('consultant',''), data.get('client',''),
         'PENDING_AI_REVIEW', json.dumps(data.get('documents', [])), json.dumps(data.get('ai_review', {})),
         '', now, now))
    conn.execute('INSERT INTO audit_log(entity_type,entity_id,actor,action,details,created_at) VALUES(?,?,?,?,?,?)',
                 ('CHECK_REQUEST', data['request_no'], data.get('actor','Contractor'), 'CREATED', json.dumps(data), now))
    conn.commit(); conn.close()
    return data['request_no']


def update_check_request(request_no, status=None, ai_review=None, human_decision=None, actor='System'):
    conn = _connect(); row = conn.execute('SELECT * FROM check_requests WHERE request_no=?', (request_no,)).fetchone()
    if not row: conn.close(); raise ValueError('Check request not found')
    sets=[]; vals=[]
    if status is not None: sets.append('status=?'); vals.append(status)
    if ai_review is not None: sets.append('ai_review=?'); vals.append(json.dumps(ai_review))
    if human_decision is not None: sets.append('human_decision=?'); vals.append(human_decision)
    sets.append('updated_at=?'); vals.append(_now()); vals.append(request_no)
    conn.execute(f"UPDATE check_requests SET {', '.join(sets)} WHERE request_no=?", vals)
    conn.execute('INSERT INTO audit_log(entity_type,entity_id,actor,action,details,created_at) VALUES(?,?,?,?,?,?)',
                 ('CHECK_REQUEST', request_no, actor, 'UPDATED', json.dumps({'status':status,'human_decision':human_decision}), _now()))
    conn.commit(); conn.close()


def list_check_requests(project=None):
    conn=_connect()
    if project:
        rows=conn.execute('SELECT * FROM check_requests WHERE project=? ORDER BY id DESC',(project,)).fetchall()
    else:
        rows=conn.execute('SELECT * FROM check_requests ORDER BY id DESC').fetchall()
    conn.close(); return [dict(r) for r in rows]


def get_check_request(request_no):
    conn=_connect(); r=conn.execute('SELECT * FROM check_requests WHERE request_no=?',(request_no,)).fetchone(); conn.close()
    return dict(r) if r else None



def create_variation(data):
    now=_now(); conn=_connect()
    conn.execute("""INSERT INTO variations
      (variation_no,project,check_request_no,boq_item,activity,original_qty,previously_approved_variation,approved_qty_before,previously_certified_qty,required_cumulative_qty,proposed_additional_qty,revised_proposed_qty,rate,estimated_value,reason,documents,ai_review,status,human_decision,submitted_by,approver,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (data['variation_no'],data['project'],data.get('check_request_no',''),data['boq_item'],data['activity'],data['original_qty'],data.get('previously_approved_variation',0),data.get('approved_qty_before',0),data.get('previously_certified_qty',0),data['required_cumulative_qty'],data['proposed_additional_qty'],data['revised_proposed_qty'],data.get('rate',0),data.get('estimated_value',0),data.get('reason',''),json.dumps(data.get('documents',[])),json.dumps(data.get('ai_review',{})),'SUBMITTED_FOR_APPROVAL','',data.get('submitted_by','Contractor'),'',now,now))
    conn.execute('INSERT INTO audit_log(entity_type,entity_id,actor,action,details,created_at) VALUES(?,?,?,?,?,?)',
                 ('VARIATION',data['variation_no'],data.get('submitted_by','Contractor'),'CREATED',json.dumps(data),now))
    conn.commit(); conn.close(); return data['variation_no']

def update_variation(variation_no,status=None,ai_review=None,human_decision=None,approver=None,actor='System'):
    conn=_connect(); row=conn.execute('SELECT * FROM variations WHERE variation_no=?',(variation_no,)).fetchone()
    if not row: conn.close(); raise ValueError('Variation not found')
    sets=[]; vals=[]
    if status is not None: sets.append('status=?'); vals.append(status)
    if ai_review is not None: sets.append('ai_review=?'); vals.append(json.dumps(ai_review))
    if human_decision is not None: sets.append('human_decision=?'); vals.append(human_decision)
    if approver is not None: sets.append('approver=?'); vals.append(approver)
    sets.append('updated_at=?'); vals.append(_now()); vals.append(variation_no)
    conn.execute(f"UPDATE variations SET {', '.join(sets)} WHERE variation_no=?",vals)
    conn.execute('INSERT INTO audit_log(entity_type,entity_id,actor,action,details,created_at) VALUES(?,?,?,?,?,?)',('VARIATION',variation_no,actor,'UPDATED',json.dumps({'status':status,'human_decision':human_decision,'approver':approver}),_now()))
    conn.commit(); conn.close()

def list_variations(project=None):
    conn=_connect()
    if project: rows=conn.execute('SELECT * FROM variations WHERE project=? ORDER BY id DESC',(project,)).fetchall()
    else: rows=conn.execute('SELECT * FROM variations ORDER BY id DESC').fetchall()
    conn.close(); return [dict(r) for r in rows]

def get_variation(variation_no):
    conn=_connect(); r=conn.execute('SELECT * FROM variations WHERE variation_no=?',(variation_no,)).fetchone(); conn.close()
    return dict(r) if r else None

def create_ipc(data):
    now=_now(); conn=_connect()
    conn.execute('''INSERT INTO ipcs
      (ipc_no,project,check_request_no,activity,period_from,period_to,current_qty,cumulative_qty,rate,current_amount,cumulative_amount,retention,net_amount,documents,ai_review,human_decision,created_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
      (data['ipc_no'],data['project'],data['check_request_no'],data['activity'],data.get('period_from',''),data.get('period_to',''),
       data['current_qty'],data['cumulative_qty'],data['rate'],data['current_amount'],data['cumulative_amount'],data['retention'],data['net_amount'],
       json.dumps(data.get('documents',[])),json.dumps(data.get('ai_review',{})),'',now))
    conn.execute('INSERT INTO audit_log(entity_type,entity_id,actor,action,details,created_at) VALUES(?,?,?,?,?,?)',
                 ('IPC',data['ipc_no'],data.get('actor','Consultant'),'CREATED',json.dumps(data),now))
    conn.commit(); conn.close(); return data['ipc_no']


def update_ipc(ipc_no, ai_review=None, human_decision=None, actor='System'):
    conn=_connect(); sets=[]; vals=[]
    if ai_review is not None: sets.append('ai_review=?'); vals.append(json.dumps(ai_review))
    if human_decision is not None: sets.append('human_decision=?'); vals.append(human_decision)
    if not sets: conn.close(); return
    vals.append(ipc_no)
    conn.execute(f"UPDATE ipcs SET {', '.join(sets)} WHERE ipc_no=?", vals)
    conn.execute('INSERT INTO audit_log(entity_type,entity_id,actor,action,details,created_at) VALUES(?,?,?,?,?,?)',
                 ('IPC',ipc_no,actor,'UPDATED',json.dumps({'human_decision':human_decision}),_now()))
    conn.commit(); conn.close()


def list_ipcs(project=None):
    conn=_connect()
    if project: rows=conn.execute('SELECT * FROM ipcs WHERE project=? ORDER BY id DESC',(project,)).fetchall()
    else: rows=conn.execute('SELECT * FROM ipcs ORDER BY id DESC').fetchall()
    conn.close(); return [dict(r) for r in rows]


def audit(entity_type=None, entity_id=None):
    conn=_connect(); q='SELECT * FROM audit_log'; p=[]; where=[]
    if entity_type: where.append('entity_type=?'); p.append(entity_type)
    if entity_id: where.append('entity_id=?'); p.append(entity_id)
    if where: q += ' WHERE ' + ' AND '.join(where)
    q += ' ORDER BY id DESC'
    rows=conn.execute(q,p).fetchall(); conn.close(); return [dict(r) for r in rows]
