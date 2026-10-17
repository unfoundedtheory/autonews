"""Telegram bot with preview uploads and version-bound edit actions."""
from pathlib import Path
import httpx
from .instagram import caption_text

def keyboard(draft):
    """Keep the preview compact; advanced editing tools live under Lainnya."""
    ref=draft.id; v=draft.version
    if draft.status=='pending_approval':
        rows=[
            [{'text':'✅ Approve','callback_data':f'approve:{ref}:{v}'},
             {'text':'❌ Tolak','callback_data':f'reject:{ref}:{v}'}],
            [{'text':'✏️ Revisi Hook','callback_data':f'highlight:{ref}:{v}'},
             {'text':'📝 Revisi Caption','callback_data':f'caption:{ref}:{v}'}],
            [{'text':'🟢 Ganti Highlight Hijau','callback_data':f'green:{ref}:{v}'}],
            [{'text':'🖼 Ganti Foto','callback_data':f'photo:{ref}:{v}'},
             {'text':'⋯ Lainnya','callback_data':f'more:{ref}:{v}'}],
        ]
    elif draft.status=='approved':
        rows=[]
        if draft.publish_state=='unpublished':
            rows.append([{'text':'📸 Post Sekarang','callback_data':f'postnow:{ref}:{v}'}])
        rows.append([{'text':'📋 Detail & Opsi','callback_data':f'more:{ref}:{v}'}])
    else:
        rows=[[{'text':'📋 Detail','callback_data':f'more:{ref}:{v}'}]]
    return {'inline_keyboard':rows}


def advanced_keyboard(draft):
    """Less common actions, opened only when the editor asks for them."""
    ref=draft.id; v=draft.version
    rows=[]
    editable=(draft.status in ('pending_approval','approved')
              and draft.publish_state not in ('publishing','published','uncertain','awaiting_container'))
    if editable:
        rows.append([
            {'text':'✨ Alternatif Hook','callback_data':f'hookideas:{ref}:{v}'},
            {'text':'✍️ Tulis Hook Sendiri','callback_data':f'manualhook:{ref}:{v}'},
        ])
        rows.append([{'text':'🎨 Render Ulang Cover','callback_data':f'redesign:{ref}:{v}'}])
    if draft.status=='pending_approval' and not draft.image_url and not draft.image_local_path:
        if 'empat baris' in (draft.last_error or '').lower():
            rows.append([{'text':'✨ Perbaiki Cover','callback_data':f'autofit:{ref}:{v}'}])
        rows.append([{'text':'🖼 Buat Cover dari Sumber','callback_data':f'retrycover:{ref}:{v}'}])
    if editable and (draft.source_image_url or draft.image_url) and (
        not draft.photo_license or not draft.image_credit):
        rows.append([{'text':'🧾 Kredit & Lisensi','callback_data':f'credit:{ref}:{v}'}])
    rows.append([
        {'text':'🔎 Sumber','callback_data':f'sources:{ref}:{v}'},
        {'text':'📋 Hasil QC','callback_data':f'qc:{ref}:{v}'},
    ])
    if draft.status=='approved' and draft.publish_state=='unpublished':
        rows.append([{'text':'📸 Posting Foto Sekarang',
                      'callback_data':f'retryig:{ref}:{v}'}])
    from .config import CONFIG
    if (CONFIG.photo_music_mode == 'manual' and
        draft.status=='approved' and
        draft.publish_state in ('unpublished','manual_music_pending') and
        not str(draft.approved_by or '').startswith('system:24h_timeout')):
        rows.append([{'text':'📦 Paket Instagram','callback_data':f'musickit:{ref}:{v}'}])
        rows.append([
            {'text':'🎵 Konfirmasi Post','callback_data':f'musicdone:{ref}:{v}'},
            {'text':'↩️ Batalkan & Revisi','callback_data':f'musiccancel:{ref}:{v}'},
        ])
    rows.append([{'text':'⬅️ Kembali','callback_data':f'actions:{ref}:{v}'}])
    return {'inline_keyboard':rows}

def main_menu():
    """Production-only navigation: no AI-consuming demo actions on the home screen."""
    return {'inline_keyboard':[
        [{'text':'📰 Generate Berita Sekarang','callback_data':'nav:generate_now'}],
        [{'text':'📝 Pending Approval','callback_data':'nav:pending'},
         {'text':'✅ Draft Disetujui','callback_data':'nav:approved'}],
        [{'text':'📅 Jadwal Posting','callback_data':'nav:queue'},
         {'text':'🗞 Kandidat Berita','callback_data':'nav:stories'}],
        [{'text':'📊 Status Otomasi','callback_data':'nav:status'},
         {'text':'🔄 Refresh Menu','callback_data':'nav:home'}]]}

def home_button():
    """One compact return-to-/start button, not the entire main menu."""
    return {'inline_keyboard': [[
        {'text':'🏠 Menu Utama','callback_data':'nav:home'}
    ]]}


def with_home_button(markup=None):
    """Append the single home action below a submenu's existing controls."""
    rows=list((markup or {}).get('inline_keyboard') or [])
    if not any(button.get('callback_data')=='nav:home'
               for row in rows for button in row):
        rows.append(home_button()['inline_keyboard'][0])
    return {'inline_keyboard':rows}


def photo_keyboard(draft):
    from .telegram_ui import photo_keyboard as make_keyboard
    return make_keyboard(draft)

class TelegramClient:
    def __init__(self,token,transport=None): self.token=token;self.transport=transport
    def call(self,method,payload):
        with httpx.Client(timeout=30,transport=self.transport) as client:
            r=client.post(f'https://api.telegram.org/bot{self.token}/{method}',json=payload)
            r.raise_for_status()
            data=r.json()
            if not data.get('ok'):raise ValueError(data.get('description','Telegram error'))
            return data['result']
    def message(self,chat_id,text,reply_markup=None):
        p={'chat_id':chat_id,'text':text[:4096],'disable_web_page_preview':True}
        if reply_markup:p['reply_markup']=reply_markup
        return self.call('sendMessage',p)
    def photo(self,chat_id,photo_url,caption,reply_markup=None):
        p={'chat_id':chat_id,'photo':photo_url,'caption':caption[:1024]}
        if reply_markup:p['reply_markup']=reply_markup
        return self.call('sendPhoto',p)
    def file_photo(self,chat_id,path,caption,reply_markup=None):
        form={'chat_id':str(chat_id),'caption':caption[:1024]}
        if reply_markup:
            import json
            form['reply_markup']=json.dumps(reply_markup)
        with open(path,'rb') as f, httpx.Client(timeout=50,transport=self.transport) as client:
            r=client.post(f'https://api.telegram.org/bot{self.token}/sendPhoto',data=form,
                          files={'photo':('preview.jpg',f,'image/jpeg')})
            r.raise_for_status()
            result=r.json()
            if not result.get('ok'):raise ValueError(result.get('description','Telegram error'))
            return result['result']
    def download_photo(self,file_id,output_path):
        """Get the original Telegram photo and validate bytes before persisting.

        Telegram photo variants are usually recompressed; the largest received
        resolution is used, while the owner can supply original URLs for photos.
        """
        from io import BytesIO
        from urllib.parse import quote
        from PIL import Image, ImageOps, UnidentifiedImageError
        meta = self.call('getFile', {'file_id': file_id})
        file_path = meta.get('file_path','')
        if not file_path or '..' in file_path.split('/') or file_path.startswith('/'):
            raise ValueError('Jalur foto Telegram tidak valid')
        if meta.get('file_size',0) > 15 * 1024 * 1024:
            raise ValueError('File foto Telegram terlalu besar')
        uri = f'https://api.telegram.org/file/bot{self.token}/{quote(file_path, safe="/")}'
        with httpx.Client(timeout=35,transport=self.transport,follow_redirects=False) as client:
            with client.stream('GET',uri) as response:
                response.raise_for_status()
                data=bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 15*1024*1024:
                        raise ValueError('Foto Telegram melebihi batas ukuran')
        try:
            with Image.open(BytesIO(data)) as im:
                if min(im.width,im.height) < 600 or im.width*im.height > 40_000_000:
                    raise ValueError('Resolusi foto Telegram tidak memenuhi syarat')
                target=Path(output_path)
                target.parent.mkdir(parents=True,exist_ok=True)
                ImageOps.exif_transpose(im).convert('RGB').save(target,'JPEG',quality=95,subsampling=0)
        except (UnidentifiedImageError,OSError) as exc:
            raise ValueError('Foto Telegram tidak terbaca') from exc
        return str(target)

    def answer(self,callback_id,text):
        return self.call('answerCallbackQuery',{'callback_query_id':callback_id,'text':text[:180],'show_alert':False})

def preview_text(d,st):
    """Clean owner-facing preview; technical details stay under the Sumber button."""
    return ('HIGHLIGHT\n'+d.highlight+'\n\n'
            'CAPTION\n'+caption_text(d,allow_missing_credit=True))



def send_preview(bot,chat_id,d,st):
    # Preview and caption are separately sent to avoid Telegram 1024-character photo caption limit.
    if d.image_local_path and Path(d.image_local_path).is_file():
        bot.file_photo(chat_id,d.image_local_path,' ')
    elif d.image_url and d.image_url.startswith('https://'):
        bot.photo(chat_id,d.image_url,' ')
    bot.message(chat_id,preview_text(d,st),keyboard(d))
