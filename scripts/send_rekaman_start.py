#!/usr/bin/env python3
"""Kirim 'Rekaman dimulai!' dari GHA record workflow.
Env: BOT_TOKEN, CHAT_ID, ORV_ID, SOURCE, HUMAN_DUR, DURATION, FILENAME
"""
import os, json, urllib.request

def main():
    bot = os.environ.get('BOT_TOKEN', '')
    chat = os.environ.get('CHAT_ID', '')
    orv = os.environ.get('ORV_ID', '')
    src = os.environ.get('SOURCE', '')
    dur = os.environ.get('HUMAN_DUR', '')
    dur_sec = int(os.environ.get('DURATION', '600') or 600)
    fname = os.environ.get('FILENAME', '')

    if not bot or not chat:
        print("⚠️ BOT_TOKEN/CHAT_ID kosong, skip.")
        return

    slabel = 'Trans7' if src == 'trans7' else 'SevenHub'
    est = max(120, dur_sec // 3)
    estm = est // 60
    mode = 'VOD biasanya cepat' if dur_sec <= 600 else 'live ~realtime'

    msg = (
        f'✅ <b>Rekaman dimulai!</b>\n\n'
        f'🆔 ID: <code>{orv}</code>\n'
        f'📺 Source: <b>{slabel}</b>\n'
        f'⏱ Durasi: {dur}\n'
        f'📦 File: {fname}\n'
        f'⏱ Target konten: {dur} (cap; {mode})\n'
        f'🎞 Estimasi encode HEVC: ~{estm} menit (workflow terpisah, ±30%)\n\n'
        f'☁️ Hasil di-upload ke GitHub Release setelah selesai, lalu dikirim ke Telegram.\n\n'
        f'Simpan ID ini untuk /cancel &lt;id&gt; kalau mau membatalkan.'
    )

    data = json.dumps({
        'chat_id': chat,
        'text': msg,
        'parse_mode': 'HTML',
    }).encode()

    for api in ['https://api.telegram.org']:
        url = f'{api}/bot{bot}/sendMessage'
        try:
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=15) as r:
                resp = json.loads(r.read().decode())
                if resp.get('ok'):
                    print(f'✅ Rekaman dimulai! sent via {api}')
                    return
                else:
                    print(f'⚠️ API error: {resp}')
        except Exception as e:
            print(f'⚠️ Failed via {api}: {e}')

    print('❌ Gagal kirim Rekaman dimulai!')

if __name__ == '__main__':
    main()
