"""Independent robot asset contracts; no changes to original pose topology."""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def test_robby_has_unique_stable_ids_and_no_embedded_media():
    source = (ROOT / 'robby/robby.svg').read_text()
    svg = ET.fromstring(source)
    assert svg.attrib['viewBox'] == '0 0 800 900'
    ids = [e.attrib['id'] for e in svg.iter() if 'id' in e.attrib]
    assert len(ids) == len(set(ids))
    assert {'body', 'head', 'eye-left', 'eye-right', 'brow-left', 'brow-right',
            'smile', 'mouth-open', 'heart', 'heart-halo'} <= set(ids)
    assert not any(e.tag.rsplit('}', 1)[-1] in {'image', 'script', 'foreignObject'}
                   for e in svg.iter())
    assert 'data:' not in source and 'http' not in source.replace('http://www.w3.org/2000/svg', '')
    assert 'NaN' not in source and 'Infinity' not in source


def test_robby_optional_camera_never_requests_microphone():
    html = (ROOT / 'robby/index.html').read_text()
    assert 'audio:false' in html
    assert 'getUserMedia' in html
    assert 'pagehide' in html
    assert '0.10.21' in html
