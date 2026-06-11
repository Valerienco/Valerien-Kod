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
import qrcode
import random
import gc  # RAM TEMİZLEYİCİ EKLENDİ

# --- SAYFA VE ARAYÜZ YAPILANDIRMASI ---
st.set_page_config(page_title="Mirrorprive_otomasyon", layout="wide")

if not os.path.exists("urun_resimleri"): os.makedirs("urun_resimleri")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;700&display=swap');
    html, body, .stApp, p, h1, h2, h3, h4, h5, h6 { font-family: 'Montserrat', sans-serif !important; }
    .stButton > button { border-radius: 0px !important; width: 100%; font-weight: 600; letter-spacing: 1px; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem !important; color: #1f2937; }
</style>
""", unsafe_allow_html=True)

st.title("Mirrorprive_otomasyon B2B Yönetim Sistemi")

# --- KURLAR VE VERİTABANI (ANTI-CRASH) ---
@st.cache_data(ttl=3600)
def kurlari_getir():
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/USD").json()
        return r["rates"]["TRY"], (r["rates"]["TRY"] / r["rates"]["EUR"]), r["rates"]["USD"]
    except: return 0, 0, 0

usd_kur, eur_kur, _ = kurlari_getir()

@st.cache_resource
def get_db_conn():
    conn = sqlite3.connect('mirrorbrand_stok.db', check_same_thread=False, timeout=30.0)
    conn.execute('''CREATE TABLE IF NOT EXISTS urunler (id INTEGER PRIMARY KEY, barkod TEXT, isim TEXT, resim_url TEXT, seri_adedi INTEGER, stok_seri INTEGER, fiyat REAL, para_birimi TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS musteriler (id INTEGER PRIMARY KEY, isim TEXT, telefon TEXT, adres TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS siparis_gecmisi (id INTEGER PRIMARY KEY, siparis_no TEXT, tarih TEXT, musteri TEXT, telefon TEXT, adres TEXT, urun_ozeti TEXT, toplam_adet INTEGER, toplam_tutar REAL, para_birimi TEXT)''')
    conn.commit()
    return conn

conn = get_db_conn()

# --- ETİKET VE İRSALİYE MOTORLARI ---
def profesyonel_etiket_olustur(barkod, isim):
    kesin_barkod = str(barkod).strip()
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=20, border=2)
    qr.add_data(kesin_barkod)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    qr_w, qr_h = qr_img.size
    etiket_w, etiket_h = qr_w + 120, qr_h + 260 
    etiket_img = Image.new('RGB', (etiket_w, etiket_h), 'white')
    draw = ImageDraw.Draw(etiket_img)
    
    font_paths = ["arialbd.ttf", "arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    f_mirror = f_isim = None
    for p in font_paths:
        try:
            f_mirror = ImageFont.truetype(p, 75)
            f_isim = ImageFont.truetype(p, 45)
            break
        except: continue
            
    if not f_mirror: f_mirror = f_isim = ImageFont.load_default()

    def metni_ortala(y_pos, metin, font, fill="black"):
        try: w = draw.textlength(metin, font=font)
        except: w = 100 
        draw.text(((etiket_w - w) / 2, y_pos), metin, fill=fill, font=font)

    metni_ortala(40, "M I R R O R", f_mirror, fill="black")
    etiket_img.paste(qr_img, ((etiket_w - qr_w) // 2, 140))
    metni_ortala(140 + qr_h + 30, str(isim)[:30], f_isim, fill="black")
    
    with io.BytesIO() as buf:
        etiket_img.save(buf, format="PNG")
        res_data = buf.getvalue()
    return res_data

def create_invoice_jpeg(order_no, date_str, customer, phone, address, cart_items, currency, raw_total, discounted_total):
    img = Image.new('RGB', (950, 1100 + (len(cart_items) * 45)), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    font_paths = ["arialbd.ttf", "arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    f_title = f_bold = f_norm = f_net = None
    for p in font_paths:
        try:
            f_title, f_bold, f_norm, f_net = ImageFont.truetype(p, 50), ImageFont.truetype(p, 26), ImageFont.truetype(p, 24), ImageFont.truetype(p, 42)
            break
        except: pass
    if not f_title: f_title = f_bold = f_norm = f_net = ImageFont.load_default()

    y = 50
    if os.path.exists("logo_sistem.png"):
        try: logo = Image.open("logo_sistem.png"); logo.thumbnail((250, 150)); img.paste(logo, (50, y)); y += logo.height + 40
        except: pass

    draw.text((50, y), "SALES ORDER RECEIPT", fill=(0,0,0), font=f_title); y += 60
    draw.text((50, y), "MIRROR BRAND WHOLESALE", fill=(100,100,100), font=f_bold); y += 35
    draw.text((50, y), "WhatsApp: +90 (533) 577 72 92", fill=(37, 211, 102), font=f_bold); y += 45
    draw.line((50, y, 900, y), fill=(0,0,0), width=3); y += 25
    
    draw.text((50, y), "TYPE: SALES RECEIPT", fill=(0,0,0), font=f_bold); y += 35
    draw.text((50, y), f"ORDER NO: {order_no}", fill=(0,0,0), font=f_bold); y += 35
    draw.text((50, y), f"DATE: {date_str}", fill=(0,0,0), font=f_bold); y += 35
    draw.text((50, y), f"CUSTOMER: {customer}", fill=(0,0,0), font=f_bold); y += 35
    if phone: draw.text((50, y), f"PHONE: {phone}", fill=(0,0,0), font=f_bold); y += 35
    
    y += 20; draw.line((50, y, 900, y), fill=(0,0,0), width=3); y += 25

    sym = "$" if "USD" in currency else ("€" if "EUR" in currency else ("₺" if "TRY" in currency else currency))
    
    draw.text((50, y), "Series", font=f_bold)
    draw.text((150, y), "Model", font=f_bold)
    draw.text((550, y), "Pcs", font=f_bold)
    draw.text((650, y), "Price", font=f_bold)
    draw.text((780, y), "Total", font=f_bold)
    y += 35
    draw.line((50, y, 900, y), fill=(200,200,200), width=2); y += 25
    
    grand_pcs = 0
    for item in cart_items:
        draw.text((50, y), f"{item['seri_miktar']}", font=f_norm)
        draw.text((150, y), f"{item['isim'][:22]}", font=f_norm)
        draw.text((550, y), f"{item['pcs']}", font=f_norm)
        draw.text((650, y), f"{item['birim_fiyat']:.2f}", font=f_norm)
        draw.text((780, y), f"{item['line_total']:.2f}", font=f_norm)
        grand_pcs += item['pcs']; y += 45
    
    y += 10; draw.line((50, y, 900, y), fill=(0,0,0), width=3); y += 25
    draw.text((450, y), f"TOTAL PCS: {grand_pcs}", font=f_bold); y += 40
    draw.text((450, y), f"TOTAL: {raw_total:.2f} {sym}", font=f_bold); y += 45
    draw.line((450, y, 900, y), fill=(200,200,200), width=2); y += 25
    draw.text((450, y), f"NET TOTAL: {discounted_total:.2f} {sym}", fill=(34,139,34), font=f_net); y += 65
    
    eq_try, eq_usd, eq_eur = 0, 0, 0
    if "USD" in currency: eq_try = discounted_total * usd_kur; eq_eur = eq_try / eur_kur if eur_kur > 0 else 0
    elif "EUR" in currency: eq_try = discounted_total * eur_kur; eq_usd = eq_try / usd_kur if usd_kur > 0 else 0
    else: eq_usd = discounted_total / usd_kur if usd_kur > 0 else 0; eq_eur = discounted_total / eur_kur if eur_kur > 0 else 0

    if eq_usd: draw.text((450, y), f"Eq USD: {eq_usd:.2f} $", fill=(120,120,120), font=f_norm); y += 35
    if eq_eur: draw.text((450, y), f"Eq EUR: {eq_eur:.2f} €", fill=(120,120,120), font=f_norm); y += 35
    if eq_try: draw.text((450, y), f"Eq TRY: {eq_try:.2f} ₺", fill=(120,120,120), font=f_norm); y += 70
    
    draw.text((50, y), "Information Receipt. Not a Financial Document.", fill=(160,160,160), font=f_norm)
    
    with io.BytesIO() as buf:
        img.save(buf, format='JPEG', quality=85, optimize=True)
        res_data = buf.getvalue()
    return res_data


# ==========================================
# ANA SİSTEM MODÜLLERİ
# ==========================================

def mod_anasayfa():
    st.header("📊 Yönetim Paneli (Kokpit)")
    with get_db_conn() as conn:
        df_sip = pd.read_sql_query("SELECT * FROM siparis_gecmisi", conn)
    
    if df_sip.empty: return st.info("Henüz satış verisi bulunmuyor.")

    toplam_ciro_usd, toplam_satilan_adet = 0, df_sip['toplam_adet'].sum()
    for _, r in df_sip.iterrows():
        t = r['toplam_tutar']
        if "USD" in r['para_birimi']: toplam_ciro_usd += t
        elif "EUR" in r['para_birimi'] and eur_kur > 0: toplam_ciro_usd += (t * eur_kur) / usd_kur
        elif "TRY" in r['para_birimi'] and usd_kur > 0: toplam_ciro_usd += t / usd_kur

    m1, m2, m3 = st.columns(3)
    m1.metric("💰 Toplam Satış Hacmi", f"{toplam_ciro_usd:,.2f} $")
    m2.metric("📦 Toplam Satılan Adet", f"{toplam_satilan_adet} Pcs")
    m3.metric("🤝 Toplam İşlem", f"{len(df_sip)} Sipariş")
    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📈 Son 10 Siparişin Tutar Dağılımı")
        son_siparisler = df_sip.tail(10).copy()
        if not son_siparisler.empty:
            st.bar_chart(data=son_siparisler, x='siparis_no', y='toplam_tutar', use_container_width=True)
            
    with c2:
        st.subheader("🔥 En Çok Satılan Kalemler")
        satilan_urunler = []
        for urunler_json in df_sip['urun_ozeti']:
            try:
                items = json.loads(urunler_json)
                for item in items: satilan_urunler.append({"Model": item['isim'], "Satılan Seri": item['seri_miktar']})
            except: pass
        
        if satilan_urunler:
            df_pop = pd.DataFrame(satilan_urunler).groupby('Model').sum().reset_index()
            df_pop = df_pop.sort_values(by='Satılan Seri', ascending=False).head(5)
            st.dataframe(df_pop, use_container_width=True, hide_index=True)


def mod_stok_durumu():
    st.header("📦 Mevcut Toptan Stoklar (Vitrin ve Finansal Özet)")
    with get_db_conn() as conn:
        df = pd.read_sql_query("SELECT * FROM urunler", conn)
        
    if df.empty: return st.info("Sistemde henüz ürün yok.")
        
    # DEPO FİNANSAL ÖZETİ
    st.subheader("🏦 Depo Finansal Özeti")
    toplam_model = len(df)
    toplam_seri = df['stok_seri'].sum()
    df['toplam_deger'] = df['seri_adedi'] * df['stok_seri'] * df['fiyat']
    
    tahmini_usd_deger = 0
    if usd_kur > 0:
        for _, r in df.iterrows():
            if "USD" in r['para_birimi']: tahmini_usd_deger += r['toplam_deger']
            elif "EUR" in r['para_birimi']: tahmini_usd_deger += (r['toplam_deger'] * eur_kur) / usd_kur
            elif "TRY" in r['para_birimi']: tahmini_usd_deger += r['toplam_deger'] / usd_kur
            
    d1, d2, d3 = st.columns(3)
    with d1: st.metric("📦 Toplam Model", f"{toplam_model} Çeşit")
    with d2: st.metric("🔢 Toplam Depo Stoğu", f"{toplam_seri} Seri")
    with d3: st.metric("💰 Toplam Tahmini Değer", f"{tahmini_usd_deger:,.2f} $")
    st.divider()

    # GELİŞMİŞ FİLTRELEME
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
    arama = f1.text_input("🔍 Arama Yap (İsim veya Kod)")
    
    kategoriler = ["Tüm Markalar"] + sorted(list(set([str(x).split()[0].upper() for x in df['isim'] if pd.notna(x) and str(x).strip() != ""])))
    sec_kat = f2.selectbox("🏷️ Marka Seç", kategoriler)
    
    turler = ["Tümü", "T-Shirt", "Şort", "Polo", "Takım"]
    sec_tur = f3.selectbox("👕 Tür Seç", turler)
    
    sirala = f4.selectbox("↕️ Sıralama", ["Yeniden Eskiye", "Alfabetik (A-Z)", "Fiyat (Düşükten Yükseğe)", "Stok (Azdan Çoğa)"])

    if sec_kat != "Tüm Markalar": 
        df = df[df['isim'].str.upper().str.startswith(sec_kat)]
        
    if sec_tur == "T-Shirt": 
        mask_tshirt = df['isim'].str.contains("t-shirt|t shirt|tshirt", case=False, regex=True, na=False)
        mask_diger = ~df['isim'].str.contains("şort|sort|polo|takım|takim|set", case=False, regex=True, na=False)
        df = df[mask_tshirt | mask_diger]
    elif sec_tur == "Şort":
        df = df[df['isim'].str.contains("şort|sort", case=False, regex=True, na=False)]
    elif sec_tur == "Takım":
        df = df[df['isim'].str.contains("takım|takim|set", case=False, regex=True, na=False)]
    elif sec_tur != "Tümü": 
        df = df[df['isim'].str.contains(sec_tur, case=False, na=False)]
        
    if arama: 
        df = df[df['isim'].str.contains(arama, case=False, na=False) | df['barkod'].str.contains(arama, case=False, na=False)]
        
    if sirala == "Alfabetik (A-Z)": df = df.sort_values(by='isim')
    elif sirala == "Fiyat (Düşükten Yükseğe)": df = df.sort_values(by='fiyat')
    elif sirala == "Stok (Azdan Çoğa)": df = df.sort_values(by='stok_seri')
    elif sirala == "Yeniden Eskiye": df = df.sort_values(by='id', ascending=False)

    URUN_SAYISI = 24
    top_sayfa = max(1, (len(df) + URUN_SAYISI - 1) // URUN_SAYISI)
    
    st.write(f"**Bulunan Model:** {len(df)}")
    aktif_sayfa = 1
    if top_sayfa > 1:
        sayfa_kolonlari = st.columns([3, 2, 3])
        with sayfa_kolonlari[1]:
            aktif_sayfa = st.number_input(f"📄 Sayfa (1 - {top_sayfa})", min_value=1, max_value=top_sayfa, value=1, step=1)
            
    st.divider()
    df_sayfa = df.iloc[(aktif_sayfa - 1) * URUN_SAYISI : aktif_sayfa * URUN_SAYISI].reset_index(drop=True)

    for i in range(0, len(df_sayfa), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(df_sayfa):
                row = df_sayfa.iloc[i+j]
                with cols[j]:
                    with st.container(border=True):
                        if row['resim_url'] and os.path.exists(row['resim_url']):
                            st.image(row['resim_url'], use_container_width=True)
                        else:
                            st.info("Görsel Yok")
                        
                        st.subheader(row['isim'])
                        st.write(f"**Kod:** {row['barkod']} | **Fiyat:** {row['fiyat']} {row['para_birimi']}")
                        
                        stok_durum = "🔴 Kritik" if row['stok_seri'] < 3 else "🟢 Yeterli"
                        st.write(f"**Stok:** {row['stok_seri']} Seri ({stok_durum}) | **İçi:** {row['seri_adedi']} Adet")
                        
                        bc1, bc2 = st.columns(2)
                        with bc1:
                            if st.button("🗑️ Sil", key=f"del_{row['id']}", use_container_width=True):
                                with get_db_conn() as conn:
                                    conn.execute("DELETE FROM urunler WHERE id=?", (int(row['id']),))
                                    conn.commit()
                                st.rerun()
                        with bc2:
                            etiket_verisi = profesyonel_etiket_olustur(row['barkod'], row['isim'])
                            st.download_button("🖨️ Etiket", data=etiket_verisi, file_name=f"MIRROR_{row['barkod']}.png", mime="image/png", key=f"qrdl_{row['id']}", use_container_width=True)
                        
                        with st.expander("✏️ Düzenle"):
                            with st.form(key=f"edit_{row['id']}"):
                                e_isim = st.text_input("Model", row['isim'])
                                e_barkod = st.text_input("Barkod (Zorunlu)", row['barkod'])
                                e_resim = st.file_uploader("📸 Yeni Fotoğraf", type=['png', 'jpg', 'jpeg'])
                                
                                c_1, c_2 = st.columns(2)
                                e_seri = c_1.selectbox("Seri Adedi", [4,5,6,7,8,10,12], index=[4,5,6,7,8,10,12].index(row['seri_adedi']) if row['seri_adedi'] in [4,5,6,7,8,10,12] else 0)
                                e_stok = c_1.number_input("Stok", value=int(row['stok_seri']))
                                e_fiyat = c_2.number_input("Fiyat", value=float(row['fiyat']))
                                e_para = c_2.selectbox("Birim", ["USD ($)", "EUR (€)", "TRY (₺)"], index=["USD ($)", "EUR (€)", "TRY (₺)"].index(row['para_birimi']) if row['para_birimi'] in ["USD ($)", "EUR (€)", "TRY (₺)"] else 0)
                                
                                if st.form_submit_button("Kaydet"):
                                    if not e_barkod.strip(): st.error("Barkod boş olamaz!")
                                    else:
                                        with get_db_conn() as conn:
                                            mevcut = conn.execute("SELECT id FROM urunler WHERE barkod=? AND id!=?", (e_barkod.strip(), int(row['id']))).fetchone()
                                            if mevcut: st.error("Barkod kullanımda!")
                                            else:
                                                yeni_yol = row['resim_url'] 
                                                if e_resim:
                                                    yeni_yol = f"urun_resimleri/{e_barkod.strip()}.jpg"
                                                    img_up = Image.open(e_resim).convert("RGB")
                                                    img_up.thumbnail((800, 800))
                                                    img_up.save(yeni_yol, "JPEG", optimize=True, quality=85)
                                                conn.execute("UPDATE urunler SET barkod=?, isim=?, resim_url=?, seri_adedi=?, stok_seri=?, fiyat=?, para_birimi=? WHERE id=?", (e_barkod.strip(), e_isim, yeni_yol, e_seri, e_stok, e_fiyat, e_para, int(row['id'])))
                                                conn.commit()
                                        st.success("Kaydedildi!"); st.rerun()

def mod_yeni_urun():
    st.header("➕ Yeni Ürün Tanımla")
    with st.form("urun_ekle"):
        isim = st.text_input("Ürün İsmi (Örn: Balenciaga Siyah T-Shirt)")
        barkod = st.text_input("Barkod (Boş bırakırsanız otomatik atanır)")
        resim = st.file_uploader("📸 Fotoğraf (Zorunlu Değil)", type=['png', 'jpg', 'jpeg'])
        
        c1, c2 = st.columns(2)
        seri, stok = c1.selectbox("Seri Adedi", [4,5,6,7,8,10,12]), c1.number_input("Depoya Girecek Stok (Seri)", min_value=0)
        para, fiyat = c2.selectbox("Birim", ["USD ($)", "EUR (€)", "TRY (₺)"]), c2.number_input("Satış Fiyatı", min_value=0.0)
        
        if st.form_submit_button("Ürünü Kaydet") and isim:
            with get_db_conn() as conn:
                if not barkod.strip(): barkod = f"MB-{random.randint(100000, 999999)}"
                mevcut = conn.execute("SELECT id FROM urunler WHERE barkod=?", (barkod.strip(),)).fetchone()
                if mevcut: st.error("⚠️ Bu barkod sistemde zaten kayıtlı!")
                else:
                    yol = ""
                    if resim:
                        yol = f"urun_resimleri/{barkod.strip()}.jpg"
                        img_up = Image.open(resim).convert("RGB")
                        img_up.thumbnail((800, 800))
                        img_up.save(yol, "JPEG", optimize=True, quality=85)
                    conn.execute("INSERT INTO urunler (barkod, isim, resim_url, seri_adedi, stok_seri, fiyat, para_birimi) VALUES (?,?,?,?,?,?,?)", (barkod.strip(), isim, yol, seri, stok, fiyat, para))
                    conn.commit()
            st.success(f"✅ Ürün başarıyla eklendi! (Kod: {barkod.strip()})")

@st.cache_data(ttl=60)
def dropdown_icin_urunleri_getir():
    with get_db_conn() as conn:
        tum_urunler = conn.execute("SELECT barkod, isim, fiyat, para_birimi FROM urunler ORDER BY isim").fetchall()
    return [f"{u[0]} - {u[1]} ({u[2]} {u[3]})" for u in tum_urunler]


# ==========================================
# RAM KONTROLLÜ SATIŞ VE KAMERA MOTORU
# ==========================================
if 'sepet' not in st.session_state: st.session_state.sepet = []
if 'son_satis_fisi' not in st.session_state: st.session_state.son_satis_fisi = None
if 'cam_key' not in st.session_state: st.session_state.cam_key = 0
if 'son_islem_mesaji' not in st.session_state: st.session_state.son_islem_mesaji = None

def mod_satis_ekrani():
    if st.session_state.get('son_satis_fisi'):
        f = st.session_state.son_satis_fisi
        st.success("✅ Satış arşive eklendi!"); st.image(f["jpeg_data"], width=400)
        c1, c2, c3 = st.columns(3)
        c1.download_button("📥 Fişi İndir", f["jpeg_data"], f["file_name"], "image/jpeg", use_container_width=True)
        if f["telefon"]: c2.link_button("📲 WhatsApp'tan Gönder", f["wa_url"], use_container_width=True)
        if c3.button("🔄 Yeni Satışa Başla", use_container_width=True): st.session_state.son_satis_fisi = None; st.rerun()
        return

    st.header("Hızlı Satış Ekranı")
    
    # Başarı mesajını ekran yenilendikten sonra da göstermek için:
    if st.session_state.son_islem_mesaji:
        st.success(st.session_state.son_islem_mesaji)
        st.session_state.son_islem_mesaji = None

    tab1, tab2 = st.tabs(["📷 Kamerayla Okut", "📝 Listeden Seçerek Ekle"])
    
    with tab1:
        st.info("💡 Ürün QR'ını kameraya okutun. Okunduktan sonra kamera kendini RAM'den temizleyip yenileyecektir.")
        
        # DİNAMİK KAMERA: Her başarılı okumada kamera id'si değişir ve eski RAM tamamen yok edilir.
        kamera = st.camera_input("📷 QR Okuyucu", key=f"kamera_modulu_{st.session_state.cam_key}")
        
        if kamera:
            try:
                with Image.open(kamera) as img:
                    decoded = decode(img)
                    
                if decoded: 
                    barkod = decoded[0].data.decode()
                    with get_db_conn() as conn:
                        urun = conn.execute("SELECT * FROM urunler WHERE barkod=?", (barkod,)).fetchone()
                        
                    if urun:
                        var_mi = False
                        for item in st.session_state.sepet:
                            if item['id'] == urun[0]:
                                item['seri_miktar'] += 1
                                item['pcs'] = item['seri_miktar'] * item['seri_ici_adet']
                                item['line_total'] = item['pcs'] * item['birim_fiyat']
                                var_mi = True
                                break
                        if not var_mi:
                            st.session_state.sepet.append({
                                'id': urun[0], 'isim': urun[2], 'resim_url': urun[3], 
                                'seri_ici_adet': urun[4], 'seri_miktar': 1, 'pcs': urun[4], 
                                'birim_fiyat': urun[6], 'line_total': urun[4]*urun[6], 'para_birimi': urun[7]
                            })
                            
                        st.session_state.son_islem_mesaji = f"✅ {urun[2]} sepete eklendi!"
                        
                        # --- İMHA PROTOKOLÜ BAŞLANGICI ---
                        st.session_state.cam_key += 1  # Kamera kimliğini değiştir
                        del kamera # Veriyi uçur
                        gc.collect() # İşletim sistemine RAM'i zorla boşalttır
                        st.rerun() # Sayfayı anında tertemiz yeniden yükle
                        # --------------------------------
                    else: 
                        st.error("❌ Bu barkoda ait ürün sistemde bulunamadı.")
                else: 
                    st.warning("⚠️ Barkod net okunamadı, tekrar çekin.")
            except Exception as e:
                st.error("Kamera işlemi sırasında bir takılma oldu, sayfayı yenileyin.")

    with tab2:
        st.info("💡 Veritabanındaki ürünleri buradan arayıp ekleyebilirsiniz.")
        urun_secenekleri = dropdown_icin_urunleri_getir()
        secilen_urun_str = st.selectbox("Eklenecek Ürünü Arayın veya Seçin", ["Lütfen Bir Ürün Seçin..."] + urun_secenekleri)
        
        if st.button("➕ Seçili Ürünü Sepete Ekle", use_container_width=True):
            if secilen_urun_str != "Lütfen Bir Ürün Seçin...":
                secilen_barkod = secilen_urun_str.split(" - ")[0]
                with get_db_conn() as conn:
                    urun = conn.execute("SELECT * FROM urunler WHERE barkod=?", (secilen_barkod,)).fetchone()
                
                if urun:
                    var_mi = False
                    for item in st.session_state.sepet:
                        if item['id'] == urun[0]:
                            item['seri_miktar'] += 1
                            item['pcs'] = item['seri_miktar'] * item['seri_ici_adet']
                            item['line_total'] = item['pcs'] * item['birim_fiyat']
                            var_mi = True
                            break
                    if not var_mi:
                        st.session_state.sepet.append({
                            'id': urun[0], 'isim': urun[2], 'resim_url': urun[3], 
                            'seri_ici_adet': urun[4], 'seri_miktar': 1, 'pcs': urun[4], 
                            'birim_fiyat': urun[6], 'line_total': urun[4]*urun[6], 'para_birimi': urun[7]
                        })
                    st.success(f"✅ {urun[2]} sepete eklendi!")
                    st.rerun()

    st.divider()
    
    if st.session_state.get('sepet'):
        ac1, ac2 = st.columns([4, 1])
        ac1.subheader("🛒 Sepet ve Satış Listesi")
        if ac2.button("🚨 Sepeti Temizle", use_container_width=True):
            st.session_state.sepet = []
            st.rerun()
            
        for i, item in enumerate(st.session_state.sepet):
            c_img, c_isim, c_seri, c_fiyat, c_sil = st.columns([2, 3, 2, 2, 1])
            
            if item.get('resim_url') and os.path.exists(item['resim_url']):
                c_img.image(item['resim_url'], width=100)
            else:
                c_img.write("Yok")
                
            c_isim.write(f"**{item['isim']}**")
            y_seri = c_seri.number_input("Seri", min_value=1, value=item['seri_miktar'], key=f"s_n_{item['id']}_{i}")
            y_fiyat = c_fiyat.number_input("Fiyat", min_value=0.0, value=float(item['birim_fiyat']), step=0.5, key=f"f_n_{item['id']}_{i}")
            
            if c_sil.button("🗑️", key=f"d_b_{item['id']}_{i}"): 
                st.session_state.sepet.pop(i)
                st.rerun()
                
            item['seri_miktar'], item['birim_fiyat'] = y_seri, y_fiyat
            item['pcs'], item['line_total'] = y_seri * item['seri_ici_adet'], y_seri * item['seri_ici_adet'] * y_fiyat

        st.divider()
        with get_db_conn() as conn:
            musteriler = conn.execute("SELECT isim, telefon, adres FROM musteriler").fetchall()
        secilen = st.selectbox("Müşteri Seçin", ["+ Yeni Müşteri Kaydet"] + [m[0] for m in musteriler])
        
        with st.form("checkout"):
            if secilen == "+ Yeni Müşteri Kaydet":
                c_m1, c_m2 = st.columns(2)
                m_isim, m_tel = c_m1.text_input("Adı*"), c_m1.text_input("Tel")
                m_adres = c_m2.text_area("Adres")
            else:
                m_isim, m_tel, m_adres = next(m for m in musteriler if m[0] == secilen)
                st.info(f"**Müşteri:** {m_isim}")

            indirim = st.number_input("İndirim (%)", 0, 100, 0)
            
            if st.form_submit_button("Satışı Onayla") and m_isim:
                try:
                    with get_db_conn() as conn:
                        if secilen == "+ Yeni Müşteri Kaydet": 
                            conn.execute("INSERT INTO musteriler (isim, telefon, adres) VALUES (?,?,?)", (m_isim, m_tel, m_adres))
                        
                        raw_total = sum([i['line_total'] for i in st.session_state.sepet])
                        disc_total = raw_total * ((100 - indirim) / 100)
                        t_adet = sum([i['pcs'] for i in st.session_state.sepet])
                        p_birim = st.session_state.sepet[0]['para_birimi']
                        sip_no, tarih = f"ORD-{datetime.now().strftime('%Y%m%d%H%M')}", datetime.now().strftime('%d/%m/%Y %H:%M')
                        
                        for i in st.session_state.sepet: 
                            conn.execute("UPDATE urunler SET stok_seri=stok_seri-? WHERE id=?", (i['seri_miktar'], i['id']))
                        
                        sepet_json = json.dumps(st.session_state.sepet)
                        conn.execute("INSERT INTO siparis_gecmisi (siparis_no, tarih, musteri, telefon, adres, urun_ozeti, toplam_adet, toplam_tutar, para_birimi) VALUES (?,?,?,?,?,?,?,?,?)",
                                  (sip_no, tarih, m_isim, m_tel, m_adres, sepet_json, t_adet, disc_total, p_birim))
                        conn.commit()
                        
                    wa_msg = urllib.parse.quote(f"Hello {m_isim},\nYour order {sip_no} is confirmed! ✔️\nTotal: {disc_total:.2f} {p_birim}")
                    st.session_state.son_satis_fisi = {
                        "jpeg_data": create_invoice_jpeg(sip_no, tarih, m_isim, m_tel, m_adres, st.session_state.sepet, p_birim, raw_total, disc_total),
                        "file_name": f"{sip_no}.jpg", "siparis_no": sip_no, "telefon": m_tel,
                        "wa_url": f"https://wa.me/{"".join(filter(str.isdigit, m_tel))}?text={wa_msg}" if m_tel else ""
                    }
                    st.session_state.sepet = []; st.session_state.islenen_qr_kodu = None; st.rerun()
                except Exception as e:
                    st.error("Sistem yoğunluğu yaşandı, lütfen tekrar deneyin.")

    else:
        st.info("Satış listesi boş. Kameradan ürün okutun veya listeden ürün seçin.")

def mod_gecmis():
    st.header("📂 Geçmiş Siparişler")
    with get_db_conn() as conn:
        df = pd.read_sql_query("SELECT id, siparis_no, tarih, musteri, toplam_adet, toplam_tutar, para_birimi FROM siparis_gecmisi ORDER BY id DESC", conn)
    if df.empty: return st.info("Arşiv boş.")
    st.dataframe(df.drop(columns=["id"]), use_container_width=True)
    
    st.divider()
    st.subheader("🔍 Geçmiş İrsaliyeleri Yeniden Çıkar veya İptal Et")
    with get_db_conn() as conn:
        siparisler = conn.execute("SELECT * FROM siparis_gecmisi ORDER BY id DESC").fetchall()
    sec_etiket = st.selectbox("İşlem Yapılacak Siparişi Seçin", [f"{s[1]} - {s[3]} ({s[2]})" for s in siparisler])
    
    if sec_etiket:
        s = next(s for s in siparisler if f"{s[1]} - {s[3]} ({s[2]})" == sec_etiket)
        
        c1, c2 = st.columns(2)
        
        if c1.button("🔄 İrsaliyeyi Tekrar Çıkar (Yeni Formatla)", use_container_width=True):
            try:
                cart_items = json.loads(s[6])
                raw_tot = sum([i['line_total'] for i in cart_items])
                jpeg_re = create_invoice_jpeg(s[1], s[2], s[3], s[4], s[5], cart_items, s[9], raw_tot, s[8])
                st.image(jpeg_re, caption=f"Yeniden Çıkarılan Fiş: {s[1]}", width=450)
                st.download_button("📥 Yeni Formatlı Fişi İndir", jpeg_re, f"Re_{s[1]}.jpg", "image/jpeg", use_container_width=True)
            except Exception as e:
                st.warning("⚠️ Bu sipariş çok eski bir formatta kaydedildiği için detayları okunamıyor.")

        if c2.button("❌ Bu Siparişi Tamamen Sil", use_container_width=True):
            with get_db_conn() as conn:
                conn.execute("DELETE FROM siparis_gecmisi WHERE id=?", (s[0],))
                conn.commit()
            st.error("🗑️ Sipariş arşivden tamamen silindi!"); st.rerun()

def mod_crm():
    st.header("📇 Müşteriler (CRM)")
    with st.form("yeni_m"):
        isim, tel, adres = st.text_input("Adı*"), st.text_input("Tel"), st.text_area("Adres")
        if st.form_submit_button("Kaydet") and isim:
            with get_db_conn() as conn:
                conn.execute("INSERT INTO musteriler (isim, telefon, adres) VALUES (?,?,?)", (isim, tel, adres))
                conn.commit()
            st.success("Eklendi!"); st.rerun()

def mod_ayarlar():
    st.header("⚙️ Ayarlar")
    logo = st.file_uploader("Logo Yükle", type=['png', 'jpg', 'jpeg'])
    if logo:
        with open("logo_sistem.png", "wb") as f: f.write(logo.getbuffer())
        st.success("Logo güncellendi!")
    if os.path.exists("logo_sistem.png"):
        st.image("logo_sistem.png", width=200)
        if st.button("Logoyu Sil"): os.remove("logo_sistem.png"); st.rerun()

# --- MENÜ SİSTEMİ ---
menu = { "🏠 Ana Sayfa": mod_anasayfa, "🛒 Hızlı Satış": mod_satis_ekrani, "📦 Stok Durumu": mod_stok_durumu, "➕ Yeni Ürün": mod_yeni_urun, "📂 Siparişler": mod_gecmis, "📇 CRM": mod_crm, "⚙️ Ayarlar": mod_ayarlar }

st.sidebar.title("Yönetim Paneli")
sec = st.sidebar.selectbox("Bölüm Seçin", list(menu.keys()))
if os.path.exists("logo_sistem.png"): st.sidebar.image("logo_sistem.png", use_container_width=True)
menu[sec]()