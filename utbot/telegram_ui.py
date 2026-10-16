"""Small, legible Telegram option menus. No embedded escaped line breaks."""
import re

PENDING_PAGE_SIZE = 5

def clean_text(value, max_chars=100):
    raw=str(value or '').replace('\\n',' ').replace('\\r',' ')
    raw=re.sub(r'\s+',' ',raw).strip()
    if len(raw)>max_chars:
        raw=raw[:max_chars-1].rstrip()+'…'
    return raw

def pending_page(drafts,total,page=0):
    max_page=max(0,(total-1)//PENDING_PAGE_SIZE)
    page=max(0,min(page,max_page))
    lines=['📝 Pending Approval',f'{total} draf • Halaman {page+1}/{max_page+1}']
    actions=[]
    if not drafts:
        lines.extend(['','Belum ada draf menunggu persetujuan.'])
    else:
        lines.append('')
        for offset,draft in enumerate(drafts,1):
            i=page*PENDING_PAGE_SIZE+offset
            lines.append(f'{i}. {clean_text(draft.highlight,98)}')
            actions.append([{'text':f'👁 Buka {i} · {draft.id[:8]}',
                             'callback_data':f'open:{draft.id}:{draft.version}'}])
    nav=[]
    if page>0:nav.append({'text':'⬅️ Sebelumnya','callback_data':f'nav:pending:{page-1}'})
    if page<max_page:nav.append({'text':'Berikutnya ➡️','callback_data':f'nav:pending:{page+1}'})
    if nav:actions.append(nav)
    if total > 0:
        actions.append([{'text':'❌ Decline All','callback_data':'nav:decline_all'}])
    actions.append([{'text':'🏠 Menu Utama','callback_data':'nav:home'}])
    return '\n'.join(lines),{'inline_keyboard':actions}

def photo_candidate_message(draft):
    lines=['🖼 Pilih Foto Cover','',
           'Pilih satu kandidat cover. Periksa objek dan hak penggunaan sebelum memilih.']
    for index,photo in enumerate((draft.photo_candidates or [])[:6],1):
        title=clean_text(photo.get('title') or 'Foto tanpa judul',75)
        title=re.sub(r'(?i)\.(?:jpe?g|png|gif|tiff?|webp)$','',title)
        lines.extend(['',f'{index}. {title}',
                      '   Kredit: '+clean_text(photo.get('credit') or 'Belum diketahui',60),
                      '   Lisensi: '+clean_text(photo.get('license') or 'Perlu diverifikasi',60)])
    return '\n'.join(lines)

def photo_keyboard(draft):
    rows=[]
    for index,photo in enumerate((draft.photo_candidates or [])[:6],1):
        buttons=[]
        url=str(photo.get('page_url') or '')
        if url.startswith('https://commons.wikimedia.org/'):
            buttons.append({'text':f'🔎 Lihat {index}','url':url})
        buttons.append({'text':f'✅ Pilih {index}',
                        'callback_data':f'pick{index-1}:{draft.id}:{draft.version}'})
        rows.append(buttons)
    rows.append([{'text':'↩️ Kembali ke Draf',
                  'callback_data':f'open:{draft.id}:{draft.version}'}])
    return {'inline_keyboard':rows}


def approved_page(drafts, total, page=0):
    """Browse live approved drafts; opening one reuses the versioned draft controls."""
    from datetime import timezone
    from .scheduler import WIB
    max_page = max(0, (total - 1) // PENDING_PAGE_SIZE)
    page = max(0, min(page, max_page))
    lines = ['✅ Draft Disetujui', f'{total} draf • Halaman {page+1}/{max_page+1}']
    actions = []
    if not drafts:
        lines.extend(['', 'Belum ada draf disetujui yang menunggu proses posting.'])
    else:
        lines.append('')
        for offset, draft in enumerate(drafts, 1):
            index = page * PENDING_PAGE_SIZE + offset
            state = draft.publish_state
            if state == 'manual_music_pending':
                label = 'Menunggu konfirmasi posting Instagram'
            elif state == 'awaiting_container':
                label = 'Menunggu container Instagram'
            elif draft.scheduled_at:
                when = draft.scheduled_at
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                label = 'Terjadwal ' + when.astimezone(WIB).strftime('%d/%m %H:%M WIB')
            else:
                label = 'Menunggu jadwal'
            lines.append(f'{index}. {clean_text(draft.highlight, 90)}')
            lines.append('   ' + label)
            actions.append([{'text':f'👁 Buka {index} · {draft.id[:8]}',
                             'callback_data':f'open:{draft.id}:{draft.version}'}])
    nav = []
    if page > 0:
        nav.append({'text':'⬅️ Sebelumnya','callback_data':f'nav:approved:{page-1}'})
    if page < max_page:
        nav.append({'text':'Berikutnya ➡️','callback_data':f'nav:approved:{page+1}'})
    if nav:
        actions.append(nav)
    actions.append([{'text':'🏠 Menu Utama','callback_data':'nav:home'}])
    return '\n'.join(lines), {'inline_keyboard':actions}


def stories_page(stories, total, page=0):
    """Read-only discovery list: source buttons never trigger a new AI request."""
    from .editorial import trusted_source
    max_page = max(0, (total - 1) // PENDING_PAGE_SIZE)
    page = max(0, min(page, max_page))
    lines = ['🗞 Kandidat Berita', f'{total} artikel tercatat • Halaman {page+1}/{max_page+1}']
    actions = []
    if not stories:
        lines.extend(['', 'Belum ada artikel ditemukan. Discovery otomatis berjalan sesuai jadwal.'])
    else:
        lines.append('')
        for offset, story in enumerate(stories, 1):
            index = page * PENDING_PAGE_SIZE + offset
            lines.append(f'{index}. {clean_text(story.title, 90)}')
            lines.append('   ' + clean_text(story.source_name, 40) +
                         ' • ' + clean_text(story.verification_status, 40))
            if trusted_source(story.source_url):
                actions.append([{'text':f'🔎 Baca Sumber {index}', 'url':story.source_url}])
    nav = []
    if page > 0:
        nav.append({'text':'⬅️ Sebelumnya','callback_data':f'nav:stories:{page-1}'})
    if page < max_page:
        nav.append({'text':'Berikutnya ➡️','callback_data':f'nav:stories:{page+1}'})
    if nav:
        actions.append(nav)
    actions.append([{'text':'🏠 Menu Utama','callback_data':'nav:home'}])
    return '\n'.join(lines), {'inline_keyboard':actions}
