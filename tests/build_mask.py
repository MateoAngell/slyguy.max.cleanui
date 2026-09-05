"""Compile the single-circle SVG UI mask to a dependency-free Kodi PNG.

Run only when the vector changes; not part of addon runtime.
"""
import math
from pathlib import Path
import struct
import zlib
import xml.etree.ElementTree as ET

media=Path(__file__).resolve().parents[1]/'resources/skins/Default/media'
root=ET.parse(media/'circle-mask.svg').getroot()
circle=root.find('{http://www.w3.org/2000/svg}circle')
w,h=int(root.get('width')),int(root.get('height'))
cx,cy,r=(float(circle.get(k)) for k in ('cx','cy','r'))
raw=bytearray()
for y in range(h):
    raw.append(0)
    for x in range(w):
        alpha=round(255*max(0,min(1,r+0.5-math.hypot(x+0.5-cx,y+0.5-cy))))
        raw.extend((255,255,255,alpha))
def chunk(kind,data):
    return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b'')
(media/'circle-mask.png').write_bytes(png)
print('Built circle-mask.png:',len(png),'bytes')
