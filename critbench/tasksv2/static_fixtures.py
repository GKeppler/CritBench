"""File-level provenance shared by the validator and sandbox configuration."""
from pathlib import Path

CRITBENCH = Path(__file__).resolve().parents[1]
FILES = {
    'siemens_scd': 'scd/KASTEL_Lab_Siemens.scd',
    'abb_scd': 'scd/KASTEL_Lab_ABB.scd',
    'rel670_cid': 'scd/ABB_REL670.cid',
    'f60_cid': 'scd/GE_F60.cid',
    'goose_trip_pcap': 'pcaps/goose_breaker_trip.pcap',
    'mms_pcapng': 'pcaps/MMS_Traffic_09-02-2024_12-58.pcapng',
    'sv_trip_pcapng': 'pcaps/Trip_Samples_Values_all_devices_240430.pcapng',
}


def declared_files(raw):
    ids = raw['fixture']['id']
    if isinstance(ids, str):
        ids = [ids]
    return {f'/code/tasks/{FILES[f]}': (CRITBENCH / 'tasks' / FILES[f]).resolve()
            for f in ids}


def mount_problems(raw, compose):
    """Reject directories, wrong source files, writable or undeclared binds."""
    import yaml
    expected = declared_files(raw)
    used = {v for v in raw['environment'].values()
            if isinstance(v, str) and v.startswith('/code/tasks/')}
    problems = []
    if used != set(expected):
        problems.append('fixture.id and environment must declare exactly the same files')
    actual = {}
    spec = yaml.safe_load(compose.read_text())
    for service in spec.get('services', {}).values():
        for mount in service.get('volumes', []):
            if isinstance(mount, str):
                parts = mount.split(':')
                source, target = parts[:2] if len(parts) >= 2 else ('', '')
                readonly = len(parts) == 3 and parts[2] == 'ro'
            else:
                source, target = mount.get('source', ''), mount.get('target', '')
                readonly = mount.get('type') == 'bind' and mount.get('read_only') is True
            host = (compose.parent / source).resolve()
            if target in actual or not readonly or not host.is_file():
                problems.append(f'invalid fixture mount: {target}')
            actual[target] = host
    if actual != expected:
        problems.append('sandbox must mount exactly the declared fixture files read-only')
    return problems
