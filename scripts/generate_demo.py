"""Preview cover with a real user-supplied, approved media file. Never fake an event photo."""
import argparse
from utbot.renderer import render

p = argparse.ArgumentParser(description='Render a real scientific photo into branded 1080x1350 post')
p.add_argument('--photo', required=True, help='Local source photograph approved for use')
p.add_argument('--output', default='outputs/preview.jpg')
p.add_argument('--headline', default='Inilah Tangan Tuhan, Struktur Sinar-X Raksasa Yang Masih Membingungkan NASA')
p.add_argument('--illustration', action='store_true', help='Disclose if this is generated illustrative imagery')
p.add_argument('--focus-x', type=float, default=0.5)
p.add_argument('--focus-y', type=float, default=0.43)
args = p.parse_args()
render(args.photo, args.headline, args.output,
       accent_words=['TANGAN', 'TUHAN', 'SINAR-X', 'RAKSASA'],
       photo_focus=(args.focus_x, args.focus_y),
       source_type='illustration' if args.illustration else 'documentary')
print(f'Preview ready: {args.output}')
