import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from pyzbar.pyzbar import decode
import requests
import os
import io
import urllib.parse
import json

# ==========================================
# 1. TEMEL FONKSİYONLAR VE VERİTABANI
# ==========================================
@st.cache_data(ttl=3600)
def kurlari_getir():
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/USD").json()
        return r["rates"]["TRY"], (r["rates"]["TRY"] / r["rates"]["EUR"]), r["rates"]["USD"]
    except:
        return 0, 0, 0

usd_kur, eur_kur, _ = kurlari_getir()

def init_db():
    conn = sqlite3.connect('mirrorbrand_stok.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS urunler (id INTEGER PRIMARY KEY, barkod TEXT, isim TEXT, resim_url TEXT, seri_adedi INTEGER, stok_seri INTEGER, fiyat REAL, para_birimi TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS musteriler (id INTEGER PRIMARY KEY, isim TEXT, telefon TEXT, adres TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS siparis_gecmisi (id INTEGER PRIMARY KEY, siparis_no TEXT, tarih TEXT, musteri TEXT, telefon TEXT, adres TEXT, urun_ozeti TEXT, toplam_adet INTEGER, toplam_tutar REAL, para_birimi TEXT)''')
    conn.commit()
    return conn, c

conn, c = init_db()

# --- İNGİLİZCE JPEG İRSALİYE MOTORU (SADECE SİMGE KULLANIMI) ---
def create_invoice_jpeg(order_no, date_str, customer, phone, address, cart_items, currency, raw_total, discounted_total):
    img = Image.new('RGB', (800, 1000 + (len(cart_items) * 40)), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        f_title = ImageFont.truetype("arialbd.ttf", 36)
        f_bold = ImageFont.truetype("arialbd.ttf", 20)
        f_norm = ImageFont.truetype("arial.ttf", 20)
        f_total = ImageFont.truetype("arialbd.ttf", 26)
        f_net = ImageFont.truetype("arialbd.ttf", 34)
    except:
        f_title = f_bold = f_norm = f_total = f_net = ImageFont.load_default()

    y = 50
    if os.path.exists("logo_sistem.png"):
        try:
            logo = Image.open("logo_sistem.png"); logo.thumbnail((250, 150)); img.paste(logo, (50, y)); y += logo.height + 40
        except: pass

    draw.text((50, y), "SALES ORDER RECEIPT", fill=(0,0,0), font=f_title); y += 45
    draw.text((50, y), "MIRROR BRAND WHOLESALE", fill=(100,100,100), font=f_bold); y += 30
    draw.text((50, y), "WhatsApp: +90 (533) 577 72 92", fill=(37, 211, 102), font=f_bold); y += 40
    draw.line((50, y, 750, y), fill=(0,0,0), width=3); y += 20
    
    draw.text((50, y), "TYPE", fill=(100,100,100), font=f_bold); draw.text((200, y), f": SALES RECEIPT", fill=(0,0,0), font=f_bold); y += 30
    draw.text((50, y), "ORDER NO", fill=(100,100,100), font=f_bold); draw.text((200, y), f": {order_no}", fill=(0,0,0), font=f_bold); y += 30
    draw.text((50, y), "DATE", fill=(100,100,100), font=f_bold); draw.text((200, y), f": {date_str}", fill=(0,0,0), font=f_bold); y += 30
    draw.text((50, y), "CUSTOMER", fill=(100,100,100), font=f_bold); draw.text((200, y), f": {customer}", fill=(0,0,0), font=f_bold); y += 30
    if phone:
        draw.text((50, y), "PHONE", fill=(100,100,100), font=f_bold); draw.text((200, y), f": {phone}", fill=(0,0,0), font=f_bold); y += 30
    
    y += 20; draw.line((50, y, 750, y), fill=(0,0,0), width=3); y += 20

    # Evrensel Simgeleri Ayıklama İşlemi
    sym = "$" if "USD" in currency else ("€" if "EUR" in currency else ("₺" if "TRY" in currency else currency))

    # YENİ TABLO BAŞLIKLARI (Tam PDF'teki gibi sadeleştirildi)
    draw.text((50, y), "Series", fill=(0,0,0), font=f_bold)
    draw.text((150, y), "Model", fill=(0,0,0), font=f_bold)
    draw.text((470, y), "Pcs", fill=(0,0,0), font=f_bold)
    draw.text((540, y), "Price", fill=(0,0,0), font=f_bold)
    draw.text((660, y), "Total", fill=(0,0,0), font=f_bold); y += 30
    draw.line((50, y, 750, y), fill=(200,200,200), width=2); y += 20
    
    grand_pcs = 0
    for item in cart_items:
        draw.text((50, y), f"{item['seri_miktar']}", fill=(0,0,0), font=f_norm)
        draw.text((150, y), f"{item['isim'][:28]}", fill=(0,0,0), font=f_norm)
        draw.text((470, y), f"{item['pcs']}", fill=(0,0,0), font=f_norm)
        draw.text((540, y), f"{item['birim_fiyat']:.2f}", fill=(0,0,0), font=f_norm)
        draw.text((660, y), f"{item['line_total']:.2f}", fill=(0,0,0), font=f_norm)
        grand_pcs += item['pcs']; y += 40
    
    y += 10; draw.line((50, y, 750, y), fill=(0,0,0), width=3); y += 20

    # ALT TOPLAMLAR (Sadece Sembol Kullanıldı)
    draw.text((350, y), "TOTAL PCS", fill=(100,100,100), font=f_bold); draw.text((550, y), f": {grand_pcs}", fill=(0,0,0), font=f_bold); y += 35
    draw.text((350, y), "TOTAL", fill=(100,100,100), font=f_bold); draw.text((550, y), f": {raw_total:.2f} {sym}", fill=(0,0,0), font=f_bold); y += 40
    
    # NET TOTAL 
    draw.line((350, y, 750, y), fill=(200,200,200), width=2); y += 20
    draw.text((350, y), "NET TOTAL", fill=(0,0,0), font=f_net); draw.text((550, y), f": {discounted_total:.2f} {sym}", fill=(34,139,34), font=f_net); y += 55
    
    eq_try, eq_usd, eq_eur = 0, 0, 0
    if "USD" in currency: eq_usd = discounted_total; eq_try = discounted_total * usd_kur; eq_eur = eq_try / eur_kur if eur_kur > 0 else 0
    elif "EUR" in currency: eq_eur = discounted_total; eq_try = discounted_total * eur_kur; eq_usd = eq_try / usd_kur if usd_kur > 0 else 0
    else: eq_try = discounted_total; eq_usd = discounted_total / usd_kur if usd_kur > 0 else 0; eq_eur = discounted_total / eur_kur if eur_kur > 0 else 0

    draw.text((350, y), f"Eq USD: {eq_usd:.2f} $", fill=(120,120,120), font=f_norm); y += 28
    draw.text((350, y), f"Eq EUR: {eq_eur:.2f} €", fill=(120,120,120), font=f_norm); y += 28
    draw.text((350, y), f"Eq TRY: {eq_try:.2f} ₺", fill=(120,120,120), font=f_norm); y += 60
    
    draw.text((50, y), "Information Receipt. Not a Financial Document.", fill=(160,160,160), font=f_norm); y += 25
    draw.text((50, y), "Bilgi Fisidir. Mali Degeri Yoktur.", fill=(160,160,160), font=f_norm)

    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG', quality=95)
    return img_byte_arr.getvalue()

# ==========================================
# 2. KOMPAKT SAYFA MODÜLLERİ
# ==========================================

def mod_stok_durumu():
    st.header("Mevcut Toptan Stoklar")
    df = pd.read_sql_query("SELECT * FROM urunler", conn)
    if df.empty: st.info("Sistemde ürün yok.")
    for _, row in df.iterrows():
        c1, c2 = st.columns([1, 4])
        if row['resim_url']: c1.image(row['resim_url'], width=150)
        c2.write(f"### {row['isim']}\n**Barkod:** {row['barkod']} | **Seri İçi:** {row['seri_adedi']} Adet | **Stok:** {row['stok_seri']} Seri\n**Birim Fiyat:** {row['fiyat']} {row['para_birimi']}")
        st.divider()

def mod_yeni_urun():
    st.header("Yeni Ürün Tanımla")
    with st.form("urun_ekle"):
        isim, barkod, resim = st.text_input("Ürün İsmi / Model Kodu"), st.text_input("Barkod"), st.text_input("Resim URL")
        c1, c2 = st.columns(2)
        seri_adedi, stok = c1.selectbox("Seri İçi Adet", [4,5,6,7,8,10,12]), c1.number_input("Stok (Seri)", min_value=0)
        para, fiyat = c2.selectbox("Para Birimi", ["USD ($)", "EUR (€)", "TRY (₺)"]), c2.number_input("Birim Fiyat (1 Adet Ürün Fiyatı)", min_value=0.0)
        if st.form_submit_button("Kaydet") and barkod and isim:
            c.execute("INSERT INTO urunler (barkod, isim, resim_url, seri_adedi, stok_seri, fiyat, para_birimi) VALUES (?,?,?,?,?,?,?)", (barkod, isim, resim, seri_adedi, stok, fiyat, para))
            conn.commit(); st.success("✅ Ürün başarıyla eklendi!")

def mod_satis_ekrani():
    if st.session_state.get('son_satis_fisi'):
        f = st.session_state.son_satis_fisi
        st.success("✅ Satış arşive eklendi!"); st.image(f["jpeg_data"], width=400)
        c1, c2, c3 = st.columns(3)
        c1.download_button("📥 Fişi İndir", f["jpeg_data"], f["file_name"], "image/jpeg", use_container_width=True)
        if f["telefon"]: c2.link_button("📲 WhatsApp'tan Gönder", f["wa_url"], use_container_width=True)
        if c3.button("🔄 Yeni Satışa Başla", use_container_width=True): st.session_state.son_satis_fisi = None; st.rerun()
        return

    st.header("Satış Ekranı")
    c1, c2 = st.columns(2)
    kamera = c1.camera_input("📷 Kamera ile Barkod Okut")
    barkod_giris = c2.text_input("✍️ Veya Barkodu Klavyeden Girip Enter'a Bas")
    barkod = (decode(Image.open(kamera))[0].data.decode() if kamera and decode(Image.open(kamera)) else None) or barkod_giris

    if barkod:
        urun = c.execute("SELECT * FROM urunler WHERE barkod=?", (barkod,)).fetchone()
        if urun:
            st.info(f"**Okunan Ürün:** {urun[2]} | **Birim Fiyat:** {urun[6]} {urun[7]}")
            if st.button("Satış Listesine / Sepete Ekle", use_container_width=True):
                st.session_state.sepet.append({'id': urun[0], 'isim': urun[2], 'seri_ici_adet': urun[4], 'seri_miktar': 1, 'pcs': urun[4], 'birim_fiyat': urun[6], 'line_total': urun[4]*urun[6], 'para_birimi': urun[7]})
                st.rerun()
        else: st.warning("Bu barkoda ait ürün bulunamadı.")

    st.divider()
    if not st.session_state.get('sepet'): return st.info("Satış listesi boş. Lütfen yukarıdan ürün okutun.")

    st.subheader("🛒 Satış Listesindeki Ürünler")
    for i, item in enumerate(st.session_state.sepet):
        col1, col2, col3, col4 = st.columns([4, 2, 2, 1])
        col1.write(f"**{item['isim']}**")
        yeni_seri = col2.number_input("Seri Adedi", min_value=1, value=item['seri_miktar'], key=f"s_{i}")
        yeni_fiyat = col3.number_input("Birim Fiyat", min_value=0.0, value=float(item['birim_fiyat']), step=0.5, key=f"f_{i}")
        if col4.button("🗑️ Satırı Sil", key=f"d_{i}"): st.session_state.sepet.pop(i); st.rerun()
        item['seri_miktar'], item['birim_fiyat'] = yeni_seri, yeni_fiyat
        item['pcs'], item['line_total'] = yeni_seri * item['seri_ici_adet'], yeni_seri * item['seri_ici_adet'] * yeni_fiyat

    st.divider()
    st.subheader("💳 Satışı Tamamla ve Müşteri Seçimi")
    musteriler = c.execute("SELECT isim, telefon, adres FROM musteriler").fetchall()
    secilen = st.selectbox("Müşteri Seçin", ["+ Yeni Müşteri Kaydet"] + [m[0] for m in musteriler])
    
    with st.form("checkout"):
        if secilen == "+ Yeni Müşteri Kaydet":
            c_m1, c_m2 = st.columns(2)
            m_isim, m_tel = c_m1.text_input("Müşteri / Firma Adı*"), c_m1.text_input("Telefon (Örn: 905...)")
            m_adres = c_m2.text_area("Adres")
        else:
            m_isim, m_tel, m_adres = next(m for m in musteriler if m[0] == secilen)
            st.info(f"**Müşteri:** {m_isim} | **Tel:** {m_tel}")

        indirim = st.number_input("Ekstra Uygulanacak Gizli İndirim (%)", 0, 100, 0)
        
        if st.form_submit_button("Satışı Onayla ve İrsaliye Çıkar") and m_isim:
            if secilen == "+ Yeni Müşteri Kaydet": c.execute("INSERT INTO musteriler (isim, telefon, adres) VALUES (?,?,?)", (m_isim, m_tel, m_adres))
            
            raw_total = sum([i['line_total'] for i in st.session_state.sepet])
            discounted_total = raw_total * ((100 - indirim) / 100)
            t_adet = sum([i['pcs'] for i in st.session_state.sepet])
            p_birim = st.session_state.sepet[0]['para_birimi']
            sip_no, tarih = f"ORD-{datetime.now().strftime('%Y%m%d%H%M')}", datetime.now().strftime('%d/%m/%Y %H:%M')
            
            for i in st.session_state.sepet: c.execute("UPDATE urunler SET stok_seri=stok_seri-? WHERE id=?", (i['seri_miktar'], i['id']))
            
            sepet_json = json.dumps(st.session_state.sepet)
            
            c.execute("INSERT INTO siparis_gecmisi (siparis_no, tarih, musteri, telefon, adres, urun_ozeti, toplam_adet, toplam_tutar, para_birimi) VALUES (?,?,?,?,?,?,?,?,?)",
                      (sip_no, tarih, m_isim, m_tel, m_adres, sepet_json, t_adet, discounted_total, p_birim))
            conn.commit()

            wa_msg = urllib.parse.quote(f"Hello {m_isim},\nYour MIRROR BRAND wholesale order {sip_no} is confirmed! ✔️\n\n📝 *Order Summary*:\n- Total Pieces: {t_adet}\n💰 *Net Total*: {discounted_total:.2f} {p_birim}\n\nThank you!")
            st.session_state.son_satis_fisi = {
                "jpeg_data": create_invoice_jpeg(sip_no, tarih, m_isim, m_tel, m_adres, st.session_state.sepet, p_birim, raw_total, discounted_total),
                "file_name": f"{sip_no}.jpg", "siparis_no": sip_no, "telefon": m_tel,
                "wa_url": f"https://wa.me/{"".join(filter(str.isdigit, m_tel))}?text={wa_msg}" if m_tel else ""
            }
            st.session_state.sepet = []; st.rerun()

def mod_gecmis():
    st.header("📂 Geçmiş Siparişler & Arşiv Detayları")
    df = pd.read_sql_query("SELECT id, siparis_no AS 'Sipariş No', tarih AS 'Tarih', musteri AS 'Müşteri', toplam_adet AS 'Toplam Adet', toplam_tutar AS 'Net Tutar', para_birimi AS 'Birim' FROM siparis_gecmisi ORDER BY id DESC", conn)
    
    if df.empty: 
        return st.info("Arşiv henüz boş.")
        
    st.dataframe(df.drop(columns=["id"]), use_container_width=True)
    st.divider()
    
    st.subheader("🔍 Sipariş İşlemleri (İncele veya Sil)")
    siparisler = c.execute("SELECT * FROM siparis_gecmisi ORDER BY id DESC").fetchall()
    sec_etiket = st.selectbox("İşlem Yapmak İstediğiniz Siparişi Seçin", [f"{s[1]} - {s[3]} ({s[2]})" for s in siparisler])
    
    if sec_etiket:
        s = next(s for s in siparisler if f"{s[1]} - {s[3]} ({s[2]})" == sec_etiket)
        siparis_id = s[0]
        
        if st.button("❌ Bu Siparişi Arşivden Tamamen Sil", use_container_width=True):
            c.execute("DELETE FROM siparis_gecmisi WHERE id=?", (siparis_id,))
            conn.commit()
            st.error("🗑️ Sipariş arşivden başarıyla silindi!")
            st.rerun()
            
        st.divider()
        
        try:
            cart_items = json.loads(s[6])
            st.write(f"**Siparişte Satılan Kalemler:**")
            df_detay = pd.DataFrame(cart_items)[['isim', 'seri_miktar', 'pcs', 'birim_fiyat', 'line_total']]
            df_detay.columns = ["Model", "Kaç Seri", "Adet (Pcs)", "Birim Fiyat", "Satır Toplamı"]
            st.dataframe(df_detay, use_container_width=True)
            
            if st.button("🔄 Bu Satışın İrsaliyesini Tekrar Çıkar", use_container_width=True):
                raw_tot = sum([i['line_total'] for i in cart_items])
                jpeg_re = create_invoice_jpeg(s[1], s[2], s[3], s[4], s[5], cart_items, s[9], raw_tot, s[8])
                st.image(jpeg_re, caption=f"Yeniden Çıkarılan Fiş: {s[1]}", width=400)
                st.download_button("📥 Bu Fişi İndir", jpeg_re, f"Re_{s[1]}.jpg", "image/jpeg", use_container_width=True)
                
        except json.JSONDecodeError:
            st.warning("⚠️ Bu sipariş eski bir formatla kaydedildiği için detayları görüntülenemiyor. İsterseniz yukarıdaki sil butonunu kullanarak bu kaydı temizleyebilirsiniz.")

def mod_urun_duzenle():
    st.header("Ürün Düzenle / Sil")
    urunler = c.execute("SELECT id, isim, barkod FROM urunler").fetchall()
    if not urunler: return st.info("Sistemde kayıtlı ürün bulunmuyor.")
    
    sec = st.selectbox("Düzenlenecek Ürünü Seçin", {f"{u[1]} ({u[2]})": u[0] for u in urunler}.keys())
    u_id = {f"{u[1]} ({u[2]})": u[0] for u in urunler}[sec]
    urun = c.execute("SELECT * FROM urunler WHERE id=?", (u_id,)).fetchone()
    
    y_isim, y_barkod = st.text_input("Ürün İsmi / Model Kodu", urun[2]), st.text_input("Barkod Numarası", urun[1])
    c1, c2 = st.columns(2)
    y_seri, y_stok = c1.selectbox("Seri İçi Ürün Adedi", [4,5,6,7,8,10,12], index=[4,5,6,7,8,10,12].index(urun[4])), c1.number_input("Güncel Stok (Seri)", value=urun[5])
    y_fiyat = c2.number_input("1 Adet Ürün Birim Fiyatı", value=urun[6])
    
    if st.button("💾 Değişiklikleri Kaydet", use_container_width=True):
        c.execute("UPDATE urunler SET barkod=?, isim=?, seri_adedi=?, stok_seri=?, fiyat=? WHERE id=?", (y_barkod, y_isim, y_seri, y_stok, y_fiyat, u_id))
        conn.commit(); st.success("✅ Ürün kaydı başarıyla güncellendi!")
    if st.button("❌ Ürünü Sistemden Tamamen Sil", use_container_width=True):
        c.execute("DELETE FROM urunler WHERE id=?", (u_id,)); conn.commit(); st.error("🗑️ Ürün veritabanından silindi!"); st.rerun()

def mod_crm():
    st.header("📇 Müşteri Veritabanı (CRM)")
    with st.form("yeni_m"):
        isim, tel, adres = st.text_input("Müşteri / Firma Adı*"), st.text_input("Telefon Numarası"), st.text_area("Adres")
        if st.form_submit_button("Müşteriyi Veritabanına Kaydet") and isim:
            c.execute("INSERT INTO musteriler (isim, telefon, adres) VALUES (?,?,?)", (isim, tel, adres))
            conn.commit(); st.success("✅ Müşteri rehbere eklendi!"); st.rerun()
    st.divider()
    
    st.subheader("📋 Kayıtlı Müşterileri Düzenle / Sil")
    musteriler = c.execute("SELECT id, isim, telefon, adres FROM musteriler").fetchall()
    if not musteriler:
        st.info("Sistemde kayıtlı müşteri bulunmuyor.")
    else:
        sec = st.selectbox("İşlem Yapılacak Müşteriyi Seçin", {f"{m[1]} ({m[2]})": m[0] for m in musteriler}.keys())
        m_id = {f"{m[1]} ({m[2]})": m[0] for m in musteriler}[sec]
        sec_m = c.execute("SELECT * FROM musteriler WHERE id=?", (m_id,)).fetchone()
        
        y_isim = st.text_input("Müşteri / Firma Adı", sec_m[1])
        y_tel = st.text_input("Telefon Numarası", sec_m[2])
        y_adres = st.text_area("Adres", sec_m[3])
        
        c1, c2 = st.columns(2)
        if c1.button("💾 Değişiklikleri Kaydet", use_container_width=True):
            c.execute("UPDATE musteriler SET isim=?, telefon=?, adres=? WHERE id=?", (y_isim, y_tel, y_adres, m_id))
            conn.commit(); st.success("✅ Müşteri başarıyla güncellendi!"); st.rerun()
        if c2.button("❌ Müşteriyi Sistemden Sil", use_container_width=True):
            c.execute("DELETE FROM musteriler WHERE id=?", (m_id,))
            conn.commit(); st.error("🗑️ Müşteri silindi!"); st.rerun()

def mod_ayarlar():
    st.header("⚙️ Kurumsal Kimlik & Mağaza Ayarları")
    logo = st.file_uploader("Şirket Logonuzu Yükleyin (PNG veya JPG)", type=['png', 'jpg', 'jpeg'])
    if logo:
        with open("logo_sistem.png", "wb") as f: f.write(logo.getbuffer())
        st.success("✅ Şirket logosu başarıyla güncellendi!")
    if os.path.exists("logo_sistem.png"):
        st.image("logo_sistem.png", width=200)
        if st.button("Mevcut Logoyu Sistemden Sil"): os.remove("logo_sistem.png"); st.rerun()

# ==========================================
# 3. ANA ARAYÜZ
# ==========================================
st.set_page_config(page_title="MIRROR BRAND Wholesale", layout="wide")
st.title("📦 MIRROR BRAND B2B Toptan Otomasyon Sistemi")

if 'sepet' not in st.session_state: st.session_state.sepet = []
if 'son_satis_fisi' not in st.session_state: st.session_state.son_satis_fisi = None

menu = {"Satış Ekranı": mod_satis_ekrani, "Stok Durumu": mod_stok_durumu, "Yeni Ürün Ekle": mod_yeni_urun, "Geçmiş Siparişler": mod_gecmis, "Ürün Düzenle / Sil": mod_urun_duzenle, "Müşteriler (CRM)": mod_crm, "Mağaza Ayarları": mod_ayarlar}
menu[st.sidebar.selectbox("Gitmek İstediğiniz Ekranı Seçin", list(menu.keys()))]()