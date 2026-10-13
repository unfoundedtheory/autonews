"""Telegram bot with preview uploads and version-bound edit actions."""
from pathlib import Path
import httpx

def keyboard(draft):
    ref=draft.id;v=draft.version
    rows=[
        [{'text':'✅ Approve','callback_data':f'approve:{ref}:{v}'},
         {'text':'❌ Tolak','callback_data':f'reject:{ref}:{v}'}],
        [{'text':'✨ Hook Alternatif','callback_data':f'hookideas:{ref}:{v}'},
         {'text':'✏️ Highlight','callback_data':f'highlight:{ref}:{v}'}],
        [
         {'text':'📝 Caption','callback_data':f'caption:{ref}:{v}'}],
        [{'text':'🖼 Ganti Foto','callback_data':f'photo:{ref}:{v}'},
         {'text':'🔎 Sumber','callback_data':f'sources:{ref}:{v}'}],
        [{'text':'📋 Hasil QC','callback_data':f'qc:{ref}:{v}'}]]
    if not draft.image_url and not draft.image_local_path and draft.status=='pending_approval':
        if 'empat baris' in (draft.last_error or '').lower():
            rows.append([{'text':'✨ Perbaiki Cover Otomatis','callback_data':f'autofit:{ref}:{v}'}])
        rows.append([{'text':'🔎 Cari Ulang Cover','callback_data':f'retrycover:{ref}:{v}'}])
    if draft.photo_license and not draft.rights_reviewed:
        rows.append([{'text':'📄 Verifikasi Hak Foto','callback_data':f'rights:{ref}:{v}'}])
    return {'inline_keyboard':rows}

def main_menu():
    return {'inline_keyboard':[
        [{'text':'📝 Pending Approval','callback_data':'nav:pending'},
         {'text':'📅 Jadwal Posting','callback_data':'nav:queue'}],
        [{'text':'📊 Status Redaksi','callback_data':'nav:status'},
         {'text':'🔄 Refresh','callback_data':'nav:home'}],
        [{'text':'🧪 Test Gemini','callback_data':'nav:test_gemini'}],
        [{'text':'📰 Generate Test News','callback_data':'nav:test_news'}]]}

def photo_keyboard(draft):
    return {'inline_keyboard':[[{'text':f'Foto {i+1}: {str(item.get("title") or "Tanpa judul")[:27]} ({(item.get("license") or "?")[:15]})',
                                'callback_data':f'pick{i}:{draft.id}:{draft.version}'}]
         for i,item in enumerate(draft.photo_candidates or [])]}

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
        from PIL import Image, UnidentifiedImageError
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
                if im.width < 800 or im.height < 800 or im.width*im.height > 40_000_000:
                    raise ValueError('Resolusi foto Telegram tidak memenuhi syarat')
                target=Path(output_path)
                target.parent.mkdir(parents=True,exist_ok=True)
                im.convert('RGB').save(target,'JPEG',quality=94)
        except (UnidentifiedImageError,OSError) as exc:
            raise ValueError('Foto Telegram tidak terbaca') from exc
        return str(target)

    def answer(self,callback_id,text):
        return self.call('answerCallbackQuery',{'callback_query_id':callback_id,'text':text[:180],'show_alert':False})

def preview_text(d,st):
    from .scheduler import WIB
    date=(d.scheduled_at.astimezone(WIB).strftime('%d %b %Y %H:%M WIB') if d.scheduled_at else 'Belum disetujui')
    rights='Sudah dikonfirmasi' if d.rights_reviewed else 'BELUM dikonfirmasi'
    return (f'📰 Unfounded Theory | Draf {d.id[:8]} v{d.version}\n'
            f'Topik: {st.topic} | Fakta: kutipan sumber primer dicocokkan otomatis\n'
            f'Hak foto: {rights} | Jadwal: {date}\n\n'
            f'HIGHLIGHT\n{d.highlight}\n\nCAPTION\n{d.caption}\n\n'
            f'{" ".join(d.hashtags)}\n\nSumber: {st.source_url}\n'
            f'Foto: {d.media_page_url or "Belum dipilih"}\nLisensi: {d.photo_license or "Belum diperiksa"}')

def send_preview(bot,chat_id,d,st):
    # Preview and caption are separately sent to avoid Telegram 1024-character photo caption limit.
    if d.image_local_path and Path(d.image_local_path).is_file():
        bot.file_photo(chat_id,d.image_local_path,f'Preview gambar untuk draf {d.id[:8]} v{d.version}')
    elif d.image_url and d.image_url.startswith('https://'):
        bot.photo(chat_id,d.image_url,f'Preview final untuk draf {d.id[:8]} v{d.version}')
    bot.message(chat_id,preview_text(d,st),keyboard(d))
