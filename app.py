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
import pytesseract
import qrcode

st.set_page_config(page_title="MIRROR BRAND B2B", layout="wide", initial_sidebar_state="expanded")

if not os.path.exists("urun_resimleri"):
    os.makedirs("urun_resimleri")

# Ortak Lüks CSS 
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;700&display=swap');
    html, body, [class*="css"], .stApp, p, h1, h2, h3, h4, h5, h6 {
        font-family: 'Montserrat', sans-serif !important;
    }
    .block-container { padding-top: 2rem !important; }
    div[data-testid="stAlert"] { border-radius: 0px !important; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    div.stButton > button:first-child { border-radius: 0px !important; font-weight: 600; letter-spacing: 1px; text-transform: uppercase; transition: all 0.3s; }
</style>
""", unsafe_allow_html=True)

st.title("MIRROR BRAND B2B Toptan Otomasyon Merkezi")

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

# --- ARGOX OS-2130D TERMAL BARKOD YAZICI MOTORU ---
def profesyonel_etiket_olustur(barkod, isim):
    # 1. Argox 203 DPI İçin Yüksek Keskinlikte QR (Saf Siyah-Beyaz)
    qr = qrcode.QRCode(
        version=1, 
        error_correction=qrcode.constants.ERROR_CORRECT_H, 
        box_size=20, # Argox'un piksellerine tam oturması için büyütüldü
        border=2     # Kenar kesilmelerini önlemek için güvenli bölge
    )
    qr.add_data(barkod)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    qr_w, qr_h = qr_img.size
    
    # 2. Etiket Kanvası (Ürün kodu kaldırıldığı için alt kısım daraltıldı)
    etiket_w = qr_w + 120
    etiket_h = qr_h + 200 # Gereksiz boşluğu aldık
    etiket_img = Image.new('RGB', (etiket_w, etiket_h), 'white')
    draw = ImageDraw.Draw(etiket_img)
    
    # 3. Termal Uyumlu Kalın Font Seçici
    font_paths = [
        "arialbd.ttf", 
        "arial.ttf", 
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
    ]
    
    f_mirror = f_isim = None
    for p in font_paths:
        try:
            f_mirror = ImageFont.truetype(p, 75)  # Çok daha büyük ve kalın MIRROR
            f_isim = ImageFont.truetype(p, 50)    # Model adı
            break
        except:
            continue
            
    if not f_mirror:
        f_mirror = f_isim = ImageFont.load_default()

    def metni_ortala(y_pos, metin, font, fill="black"):
        try:
            w = draw.textlength(metin, font=font)
        except:
            w = 100 
        x_pos = (etiket_w - w) / 2
        draw.text((x_pos, y_pos), metin, fill=fill, font=font)

    # 4. Argox Optimizasyonlu Çizim (Gri renk yasak, her şey SAF SİYAH)
    metni_ortala(30, "M I R R O R", f_mirror, fill="black")
    
    etiket_img.paste(qr_img, ((etiket_w - qr_w) // 2, 130))
    
    isim_temiz = isim[:25]
    metni_ortala(130 + qr_h + 20, isim_temiz, f_isim, fill="black")
    # KOD: {barkod} kısmı tamamen kaldırıldı
    
    buf = io.BytesIO()
    etiket_img.save(buf, format="PNG")
    return buf.getvalue()

# --- İNGİLİZCE JPEG İRSALİYE MOTORU ---
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

    sym = "$" if "USD" in currency else ("€" if "EUR" in currency else ("₺" if "TRY" in currency else currency))

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

    draw.text((350, y), "TOTAL PCS", fill=(100,100,100), font=f_bold); draw.text((550, y), f": {grand_pcs}", fill=(0,0,0), font=f_bold); y += 35
    draw.text((350, y), "TOTAL", fill=(100,100,100), font=f_bold); draw.text((550, y), f": {raw_total:.2f} {sym}", fill=(0,0,0), font=f_bold); y += 40
    
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

def mod_anasayfa():
    st.header("📊 Yönetim Paneli (Kokpit)")
    
    df_sip = pd.read_sql_query("SELECT * FROM siparis_gecmisi", conn)
    df_urun = pd.read_sql_query("SELECT * FROM urunler", conn)
    
    if df_sip.empty:
        st.info("Sistemde henüz satış verisi bulunmuyor. Satış yaptıkça grafikler burada oluşacaktır.")
        return

    toplam_ciro_usd = 0
    toplam_satilan_adet = df_sip['toplam_adet'].sum()
    
    for _, r in df_sip.iterrows():
        tutar = r['toplam_tutar']
        if "USD" in r['para_birimi']: toplam_ciro_usd += tutar
        elif "EUR" in r['para_birimi'] and eur_kur > 0: toplam_ciro_usd += (tutar * eur_kur) / usd_kur
        elif "TRY" in r['para_birimi'] and usd_kur > 0: toplam_ciro_usd += tutar / usd_kur

    m1, m2, m3 = st.columns(3)
    m1.metric("💰 Toplam Satış Hacmi (Tahmini)", f"{toplam_ciro_usd:,.2f} $")
    m2.metric("📦 Toplam Satılan Adet", f"{toplam_satilan_adet} Pcs")
    m3.metric("🤝 Toplam İşlem (Fiş)", f"{len(df_sip)} Sipariş")
    
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
                for item in items:
                    satilan_urunler.append({"Model": item['isim'], "Satılan Seri": item['seri_miktar']})
            except: pass
        
        if satilan_urunler:
            df_pop = pd.DataFrame(satilan_urunler).groupby('Model').sum().reset_index()
            df_pop = df_pop.sort_values(by='Satılan Seri', ascending=False).head(5)
            st.dataframe(df_pop, use_container_width=True, hide_index=True)

def mod_stok_durumu():
    st.header("Mevcut Toptan Stoklar (Grid Vitrin)")
    df = pd.read_sql_query("SELECT * FROM urunler", conn)
    
    if df.empty: 
        return st.info("Sistemde henüz ürün yok.")
        
    st.subheader("🏦 Depo Finansal Özeti")
    toplam_model = len(df)
    toplam_seri = df['stok_seri'].sum()
    df['toplam_deger'] = df['seri_adedi'] * df['stok_seri'] * df['fiyat']
    
    tahmini_usd_deger = 0
    for _, r in df.iterrows():
        if "USD" in r['para_birimi']: tahmini_usd_deger += r['toplam_deger']
        elif "EUR" in r['para_birimi'] and eur_kur > 0: tahmini_usd_deger += (r['toplam_deger'] * eur_kur) / usd_kur
        elif "TRY" in r['para_birimi'] and usd_kur > 0: tahmini_usd_deger += r['toplam_deger'] / usd_kur
        
    d1, d2, d3 = st.columns(3)
    d1.metric("📦 Toplam Model", f"{toplam_model} Çeşit")
    d2.metric("🔢 Toplam Stok", f"{toplam_seri} Seri")
    d3.metric("💰 Tahmini Depo Değeri", f"{tahmini_usd_deger:,.2f} $")
    st.divider()

    f1, f2, f3 = st.columns([2, 1, 1])
    arama = f1.text_input("🔍 Arama Yap (İsim veya Barkod)")
    kategoriler = ["Tüm Markalar"] + sorted(list(set([str(x).split()[0].upper() for x in df['isim'] if pd.notna(x) and str(x).strip() != ""])))
    secili_kategori = f2.selectbox("🏷️ Kategori / Marka Seç", kategoriler)
    siralama = f3.selectbox("↕️ Sıralama Ölçütü", ["Yeniden Eskiye", "Alfabetik (A-Z)", "Fiyat (Düşükten Yükseğe)", "Fiyat (Yüksekten Düşüğe)", "Stok (Azdan Çoğa)"])

    if secili_kategori != "Tüm Markalar": df = df[df['isim'].str.upper().str.startswith(secili_kategori)]
    if arama: df = df[df['isim'].str.contains(arama, case=False, na=False) | df['barkod'].str.contains(arama, case=False, na=False)]
    if siralama == "Alfabetik (A-Z)": df = df.sort_values(by='isim')
    elif siralama == "Fiyat (Düşükten Yükseğe)": df = df.sort_values(by='fiyat')
    elif siralama == "Fiyat (Yüksekten Düşüğe)": df = df.sort_values(by='fiyat', ascending=False)
    elif siralama == "Stok (Azdan Çoğa)": df = df.sort_values(by='stok_seri')
    elif siralama == "Yeniden Eskiye": df = df.sort_values(by='id', ascending=False)

    URUN_SAYISI_SAYFA = 24
    toplam_sayfa = max(1, (len(df) + URUN_SAYISI_SAYFA - 1) // URUN_SAYISI_SAYFA)
    
    st.write(f"**Bulunan Toplam Model:** {len(df)}")
    
    if toplam_sayfa > 1:
        sayfa_kolonlari = st.columns([3, 2, 3])
        with sayfa_kolonlari[1]:
            aktif_sayfa = st.number_input(f"📄 Sayfa (1 - {toplam_sayfa})", min_value=1, max_value=toplam_sayfa, value=1, step=1)
    else:
        aktif_sayfa = 1
        
    st.divider()

    baslangic_index = (aktif_sayfa - 1) * URUN_SAYISI_SAYFA
    bitis_index = baslangic_index + URUN_SAYISI_SAYFA
    df_sayfa = df.iloc[baslangic_index:bitis_index].reset_index(drop=True)

    for i in range(0, len(df_sayfa), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(df_sayfa):
                row = df_sayfa.iloc[i+j]
                with cols[j]:
                    with st.container(border=True):
                        if row['resim_url']:
                            try: st.image(row['resim_url'], use_container_width=True)
                            except Exception: st.error("Resim bulunamadı.")
                        
                        st.subheader(row['isim'])
                        st.write(f"**Kod:** {row['barkod']}")
                        st.write(f"**Fiyat:** {row['fiyat']} {row['para_birimi']}")
                        
                        stok_renk = "🔴 Kritik Stok" if row['stok_seri'] <= 2 else "🟢 Yeterli"
                        st.write(f"**Stok:** {row['stok_seri']} Seri ({stok_renk}) | **Seri İçi:** {row['seri_adedi']} Adet")
                        
                        bc1, bc2 = st.columns(2)
                        with bc1:
                            if st.button("🗑️ Sil", key=f"del_{row['id']}", use_container_width=True):
                                c.execute("DELETE FROM urunler WHERE id=?", (int(row['id']),))
                                conn.commit(); st.rerun()
                                
                        with bc2:
                            # --- YENİ ETİKET MOTORU ÇAĞRISI ---
                            etiket_verisi = profesyonel_etiket_olustur(row['barkod'], row['isim'])
                            st.download_button("🖨️ Etiket İndir", data=etiket_verisi, file_name=f"MIRROR_{row['barkod']}.png", mime="image/png", key=f"qrdl_{row['id']}", use_container_width=True)
                        
                        with st.expander("👁️ Etiketi Göster"):
                            st.image(etiket_verisi, use_container_width=True)
                            
                        with st.expander("✏️ Düzenle"):
                            with st.form(key=f"edit_{row['id']}"):
                                e_isim = st.text_input("Model Kodu", row['isim'], key=f"isim_{row['id']}")
                                e_barkod = st.text_input("Barkod", row['barkod'], key=f"barkod_{row['id']}")
                                e_resim_dosyasi = st.file_uploader("📸 Yeni Fotoğraf", type=['png', 'jpg', 'jpeg'], key=f"up_{row['id']}")
                                
                                seriler = [4, 5, 6, 7, 8, 10, 12]
                                e_seri = st.selectbox("Seri İçi Adet", seriler, index=seriler.index(row['seri_adedi']) if row['seri_adedi'] in seriler else 0, key=f"seri_{row['id']}")
                                e_stok = st.number_input("Güncel Stok", value=int(row['stok_seri']), key=f"stok_{row['id']}")
                                e_fiyat = st.number_input("Birim Fiyat", value=float(row['fiyat']), key=f"fiyat_{row['id']}")
                                paralar = ["USD ($)", "EUR (€)", "TRY (₺)"]
                                e_para = st.selectbox("Para Birimi", paralar, index=paralar.index(row['para_birimi']) if row['para_birimi'] in paralar else 0, key=f"para_{row['id']}")
                                
                                if st.form_submit_button("Kaydet"):
                                    yeni_yol = row['resim_url'] 
                                    if e_resim_dosyasi is not None:
                                        yeni_yol = f"urun_resimleri/{e_barkod}.jpg"
                                        with open(yeni_yol, "wb") as f: f.write(e_resim_dosyasi.getbuffer())
                                    
                                    c.execute("UPDATE urunler SET barkod=?, isim=?, resim_url=?, seri_adedi=?, stok_seri=?, fiyat=?, para_birimi=? WHERE id=?", 
                                              (e_barkod, e_isim, yeni_yol, e_seri, e_stok, e_fiyat, e_para, int(row['id'])))
                                    conn.commit()
                                    st.success("Güncellendi!")
                                    st.rerun()

def mod_yeni_urun():
    st.header("Yeni Ürün Tanımla")
    with st.form("urun_ekle"):
        isim = st.text_input("Ürün İsmi / Model Kodu")
        barkod = st.text_input("Barkod")
        
        resim_dosyasi = st.file_uploader("📸 Ürün Fotoğrafı Yükle (Zorunlu Değil, Tıklayıp Seçin)", type=['png', 'jpg', 'jpeg'])
        
        c1, c2 = st.columns(2)
        seri_adedi, stok = c1.selectbox("Seri İçi Adet", [4,5,6,7,8,10,12]), c1.number_input("Stok (Seri)", min_value=0)
        para, fiyat = c2.selectbox("Para Birimi", ["USD ($)", "EUR (€)", "TRY (₺)"]), c2.number_input("Birim Fiyat (1 Adet Ürün Fiyatı)", min_value=0.0)
        
        if st.form_submit_button("Kaydet") and barkod and isim:
            mevcut_urun = c.execute("SELECT id FROM urunler WHERE barkod=?", (barkod,)).fetchone()
            
            if mevcut_urun:
                st.error("⚠️ Hata: Bu barkod / model koduna sahip bir ürün zaten var! Aynı barkodu iki kez ekleyemezsiniz.")
            else:
                kaydedilecek_resim_yolu = ""
                if resim_dosyasi is not None:
                    kaydedilecek_resim_yolu = f"urun_resimleri/{barkod}.jpg"
                    with open(kaydedilecek_resim_yolu, "wb") as f:
                        f.write(resim_dosyasi.getbuffer())
                
                c.execute("INSERT INTO urunler (barkod, isim, resim_url, seri_adedi, stok_seri, fiyat, para_birimi) VALUES (?,?,?,?,?,?,?)", (barkod, isim, kaydedilecek_resim_yolu, seri_adedi, stok, fiyat, para))
                conn.commit()
                st.success("✅ Ürün başarıyla eklendi!")

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
    okuma_secenegi = st.radio("Okutma Yöntemi Seçin:", ["Klavyeden Elle Gir / Bluetooth Tabanca", "Barkod / Karekod Oku", "Düz Yazı Oku (OCR)"])
    barkod = None
    
    if okuma_secenegi == "Klavyeden Elle Gir / Bluetooth Tabanca":
        barkod = st.text_input("✍️ Ürün Kodunu Girip Enter'a Basın")
        
    elif okuma_secenegi == "Barkod / Karekod Oku":
        kamera = st.camera_input("📷 Çizgili Barkod / Karekod Okut")
        if kamera:
            decoded = decode(Image.open(kamera))
            if decoded:
                barkod = decoded[0].data.decode()
            else:
                st.warning("Barkod okunamadı.")
                
    elif okuma_secenegi == "Düz Yazı Oku (OCR)":
        st.info("Kamerayı ürün kodunun tam karşısında tutun. Sadece orta yatay alan okunur.")
        kamera_ocr = st.camera_input("📷 Ürün Kodunun Fotoğrafını Çekin")
        if kamera_ocr:
            img = Image.open(kamera_ocr)
            genislik, yukseklik = img.size
            kirpilmis_img = img.crop((0, yukseklik * 0.35, genislik, yukseklik * 0.65))
            st.image(kirpilmis_img, caption="Okunan Yatay Alan")
            okunan_metin = pytesseract.image_to_string(kirpilmis_img).strip()
            if okunan_metin:
                barkod = okunan_metin
            else:
                st.error("Yazı okunamadı. Lütfen tam ortalayıp tekrar çekin.")

    if barkod:
        urun = c.execute("SELECT * FROM urunler WHERE barkod=?", (barkod,)).fetchone()
        if urun:
            sc1, sc2 = st.columns([1, 4])
            with sc1:
                if urun[3]: 
                    try: st.image(urun[3], width=120)
                    except Exception: st.warning("Resim bulunamadı.")
            
            with sc2:
                st.info(f"**Okunan Ürün:** {urun[2]} | **Birim Fiyat:** {urun[6]} {urun[7]}")
                if st.button("Satış Listesine / Sepete Ekle", use_container_width=True):
                    st.session_state.sepet.append({'id': urun[0], 'isim': urun[2], 'seri_ici_adet': urun[4], 'seri_miktar': 1, 'pcs': urun[4], 'birim_fiyat': urun[6], 'line_total': urun[4]*urun[6], 'para_birimi': urun[7]})
                    st.rerun()
        else: 
            st.warning("Bu barkoda ait ürün bulunamadı.")

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
# 3. ANA ARAYÜZ VE MENÜ
# ==========================================
if 'sepet' not in st.session_state: st.session_state.sepet = []
if 'son_satis_fisi' not in st.session_state: st.session_state.son_satis_fisi = None

menu = {
    "🏠 Ana Sayfa (Kokpit)": mod_anasayfa,
    "🛒 Satış Ekranı": mod_satis_ekrani, 
    "📦 Stok Durumu (Vitrin)": mod_stok_durumu, 
    "➕ Yeni Ürün Ekle": mod_yeni_urun, 
    "📂 Geçmiş Siparişler": mod_gecmis, 
    "📇 Müşteriler (CRM)": mod_crm, 
    "⚙️ Mağaza Ayarları": mod_ayarlar
}

st.sidebar.title("Yönetim Paneli")
secilen_ekran = st.sidebar.selectbox("Gideceğiniz Ekranı Seçin", list(menu.keys()))
st.sidebar.divider()

if os.path.exists("logo_sistem.png"):
    st.sidebar.image("logo_sistem.png", use_container_width=True)

menu[secilen_ekran]()