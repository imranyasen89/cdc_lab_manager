"""Sample containers (vials) a branch can pick per patient, and integrity options."""

# code: (label, sample_type stored on Sample, colour (hex) of the cap/icon, typical tests)
CONTAINERS = [
    ('EDTA',     'EDTA (Purple)',     'Blood (EDTA)',     '#7c3aed', 'CBC, ESR, HbA1c'),
    ('SST',      'Yellow (Gel/SST)',  'Blood (Serum)',    '#eab308', 'LFT, RFT, Lipids, Hormones'),
    ('CITRATE',  'Citrate (Blue)',    'Blood (Citrate)',  '#0ea5e9', 'PT/INR, APTT'),
    ('FLUORIDE', 'Fluoride (Grey)',   'Blood (Fluoride)', '#64748b', 'Glucose'),
    ('PLAIN',    'Plain (Red)',       'Blood (Plain)',    '#dc2626', 'Serology'),
    ('URINE',    'Urine',             'Urine',            '#f59e0b', 'Urine R/E, C/S'),
    ('STOOL',    'Stool',             'Stool',            '#92400e', 'Stool R/E, C/S'),
    ('SWAB',     'Swab',              'Swab',             '#10b981', 'Culture'),
    ('OTHER',    'Other',             'Other',            '#475569', ''),
]

CONTAINER_BY_CODE = {c[0]: c for c in CONTAINERS}

CONDITIONS = ['Good', 'Hemolyzed', 'Clotted', 'Lipemic', 'Insufficient Volume',
              'Leaking', 'Unlabeled / Mislabeled', 'Delayed']


def container_info(code, sample_type=None):
    """Return dict(label, color) for display; falls back to the stored sample type."""
    c = CONTAINER_BY_CODE.get(code or '')
    if c:
        label = c[1] if code != 'OTHER' or not sample_type or sample_type == 'Other' else sample_type
        return {'code': code, 'label': label, 'color': c[3]}
    for c in CONTAINERS:  # older rows saved before containers existed
        if c[2] == sample_type:
            return {'code': c[0], 'label': c[1], 'color': c[3]}
    return {'code': 'OTHER', 'label': sample_type or 'Sample', 'color': '#475569'}
