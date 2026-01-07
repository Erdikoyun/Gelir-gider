import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime
import random
import os
import sqlite3
from typing import List, Dict, Any

# Database file
DB_PATH = os.getenv("DATABASE_URL", os.path.join(os.path.dirname(__file__), 'findash.db'))

# Ensure DB file and tables exist early
_conn = sqlite3.connect(DB_PATH)
_cur = _conn.cursor()
_cur.execute(
    """
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        date TEXT,
        type TEXT,
        category TEXT,
        amount REAL,
        description TEXT,
        payment_method TEXT
    )
    """
)
# Bank hesapları tablosuna type sütunu ekle
_cur.execute(
    """
    CREATE TABLE IF NOT EXISTS bank_accounts (
        id TEXT PRIMARY KEY,
        name TEXT,
        balance REAL,
        currency TEXT,
        account_type TEXT
    )
    """
)
_conn.commit()
_conn.close()

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Chill",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STİL VE CSS ---
st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    .bank-card {
        background-color: #e6f3ff;
        border: 1px solid #c7e6ff;
        padding: 12px;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        color: #0f172a;
    }
    div[data-testid="stMetric"] {
        background-color: #e6f3ff;
        border: 1px solid #c7e6ff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        color: #0f172a;
    }
    div[data-testid="stMetric"] * { color: inherit !important; }
    [data-theme="dark"] .bank-card {
        background-color: #072033;
        border: 1px solid #12394a;
        color: #e6eef8;
    }
    [data-theme="dark"] div[data-testid="stMetric"] {
        background-color: #072033;
        border: 1px solid #12394a;
        color: #e6eef8;
    }
    [data-theme="dark"] div[data-testid="stMetric"] * { color: inherit !important; }
    div[data-testid="stPlotlyChart"] > div {
        border-radius: 14px;
        overflow: hidden;
        background-color: #803811;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    div[data-testid="stPlotlyChart"] .plotly-graph-div {
        background-color: transparent !important;
    }
</style>
""", unsafe_allow_html=True)

# --- YARDIMCI FONKSİYONLAR ---

def get_transaction_categories():
    return ["Maaş", "Kira", "Eğlence", "Alışveriş", "Kıyafet", "Yemek", "Sağlık", "Seyahat"]

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY,
            date TEXT,
            type TEXT,
            category TEXT,
            amount REAL,
            description TEXT,
            payment_method TEXT
        )
        """
    )
    try:
        cur.execute("ALTER TABLE transactions ADD COLUMN payment_method TEXT")
    except sqlite3.OperationalError:
        pass
    
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bank_accounts (
            id TEXT PRIMARY KEY,
            name TEXT,
            balance REAL,
            currency TEXT,
            account_type TEXT
        )
        """
    )
    # Banka hesaplarına type sütunu ekle (Migration)
    try:
        cur.execute("ALTER TABLE bank_accounts ADD COLUMN account_type TEXT DEFAULT 'Banka'")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()

def load_transactions_from_db():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM transactions ORDER BY date DESC", conn, parse_dates=['date'])
    conn.close()
    return df

def load_bank_accounts_from_db() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM bank_accounts")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def insert_account_db(acc: dict):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO bank_accounts(id, name, balance, currency, account_type) VALUES (?, ?, ?, ?, ?)",
                (acc['id'], acc['name'], acc['balance'], acc['currency'], acc['account_type']))
    conn.commit()
    conn.close()

def delete_account_db(acc_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM bank_accounts WHERE id = ?", (acc_id,))
    conn.commit()
    conn.close()

def get_transaction_by_id(tx_id: str) -> Dict[str, Any]:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    try:
        d['date'] = pd.to_datetime(d['date'])
    except Exception:
        pass
    return d

def update_transaction_db(tx_id: str, t_type: str, amount: float, category: str, date_val, desc: str, payment_method: str):
    old_tx = get_transaction_by_id(tx_id)
    
    if old_tx:
        reverse_type = 'Expense' if old_tx['type'] == 'Income' else 'Income'
        adjust_account_balance(old_tx.get('payment_method'), old_tx['amount'], reverse_type)

    adjust_account_balance(payment_method, float(amount), t_type)

    date_iso = pd.to_datetime(date_val).isoformat()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE transactions SET date = ?, type = ?, category = ?, amount = ?, description = ?, payment_method = ? WHERE id = ?",
        (date_iso, t_type, category, float(amount), desc, payment_method, tx_id)
    )
    conn.commit()
    conn.close()

def delete_transaction_db(tx_id: str):
    tx = get_transaction_by_id(tx_id)
    
    if tx:
        reverse_type = 'Expense' if tx['type'] == 'Income' else 'Income'
        adjust_account_balance(tx.get('payment_method'), tx['amount'], reverse_type)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
        conn.commit()
        conn.close()

def clear_and_seed_demo_db():
    init_db()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions")
    cur.execute("DELETE FROM bank_accounts")
    conn.commit()

    # Seed various account types
    demo_accounts = [
        {'id': '1', 'name': 'Ziraat Bankası', 'balance': 15400.50, 'currency': 'TRY', 'account_type': 'Banka'},
        {'id': '2', 'name': 'Garanti BBVA', 'balance': 4200.00, 'currency': 'TRY', 'account_type': 'Banka'},
        {'id': '3', 'name': 'İş Bankası', 'balance': 250.00, 'currency': 'USD', 'account_type': 'Banka'},
        {'id': '4', 'name': 'Bonus Kredi Kartı', 'balance': -1200.00, 'currency': 'TRY', 'account_type': 'Kredi Kartı'},
        {'id': '5', 'name': 'Cüzdan', 'balance': 500.00, 'currency': 'TRY', 'account_type': 'Nakit'},
        {'id': '6', 'name': 'Sodexo', 'balance': 450.00, 'currency': 'TRY', 'account_type': 'Yemek Kartı'}
    ]
    for a in demo_accounts:
        cur.execute("INSERT INTO bank_accounts(id, name, balance, currency, account_type) VALUES (?, ?, ?, ?, ?)",
                    (a['id'], a['name'], a['balance'], a['currency'], a['account_type']))

    demo_payment_methods = ['Cüzdan', 'Bonus Kredi Kartı', 'Sodexo', 'Ziraat Bankası', 'Garanti BBVA']
    demo_categories = ['Maaş', 'Kira', 'Eğlence', 'Alışveriş', 'Kıyafet', 'Yemek', 'Sağlık', 'Seyahat']
    
    today = datetime.date.today()
    for i in range(60):
        date = today - datetime.timedelta(days=i)
        daily_count = random.randint(1, 3)
        for _ in range(daily_count):
            is_income = random.random() > 0.7
            t_type = 'Income' if is_income else 'Expense'
            category = random.choice(demo_categories) if not is_income else "Maaş" 
            amount = random.uniform(500, 2500) if is_income else random.uniform(50, 400)
            p_method = random.choice(demo_payment_methods)
            cur.execute(
                "INSERT INTO transactions(id, date, type, category, amount, description, payment_method) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(random.randint(10000, 99999)), pd.to_datetime(date).isoformat(), t_type, category, round(amount, 2), f"Demo {t_type}", p_method)
            )
            
            if p_method in [acc['name'] for acc in demo_accounts]:
                target_name = p_method
                multiplier = 1 if t_type == 'Income' else -1
                for acc in demo_accounts:
                    if acc['name'] == target_name:
                        acc['balance'] += amount * multiplier
                        
    cur.execute("DELETE FROM bank_accounts")
    for a in demo_accounts:
        cur.execute("INSERT INTO bank_accounts(id, name, balance, currency, account_type) VALUES (?, ?, ?, ?, ?)",
                    (a['id'], a['name'], a['balance'], a['currency'], a['account_type']))

    conn.commit()
    conn.close()

def clear_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions")
    cur.execute("DELETE FROM bank_accounts")
    conn.commit()
    conn.close()

def get_total_assets():
    total = 0
    for acc in st.session_state.bank_accounts:
        rate = 30 if acc['currency'] == 'USD' else (33 if acc['currency'] == 'EUR' else 1)
        total += acc['balance'] * rate
    return total

def get_payment_methods():
    """Returns a list of payment methods: All accounts from DB."""
    if 'bank_accounts' in st.session_state:
        return [acc['name'] for acc in st.session_state.bank_accounts]
    return []

def adjust_account_balance(payment_method_name, amount, transaction_type):
    """Adjusts account balance based on transaction type."""
    accounts = load_bank_accounts_from_db()
    target_acc = None
    
    for acc in accounts:
        if acc['name'] == payment_method_name:
            target_acc = acc
            break
    
    if target_acc:
        multiplier = 1 if transaction_type == 'Income' else -1
        new_balance = target_acc['balance'] + (amount * multiplier)
        
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("UPDATE bank_accounts SET balance = ? WHERE id = ?", (new_balance, target_acc['id']))
        conn.commit()
        conn.close()
        
        st.session_state.bank_accounts = load_bank_accounts_from_db()
        return True
    return False

def add_transaction(t_type, amount, category, date, desc, payment_method):
    new_id = str(random.randint(10000, 99999))
    date_iso = pd.to_datetime(date).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transactions(id, date, type, category, amount, description, payment_method) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_id, date_iso, t_type, category, amount, desc, payment_method)
    )
    conn.commit()
    conn.close()

    adjust_account_balance(payment_method, amount, t_type)
    st.session_state.transactions = load_transactions_from_db()

# --- HESAP YÖNETİMİ SAYFA GÖRÜNÜMÜ FONKSİYONU ---
def render_account_manager(page_title, account_type):
    st.subheader(page_title)
    
    with st.expander(f"Yeni {page_title} Ekle", expanded=True):
        with st.form(f"add_{account_type.replace(' ', '_')}_form"):
            c1, c2, c3 = st.columns(3)
            with c1: b_name = st.text_input("Hesap Adı")
            with c2: b_bal = st.number_input("Bakiye", min_value=0.0, value=0.0)
            with c3: b_curr = st.selectbox("Para Birimi", ["TRY", "USD", "EUR"])
            
            if st.form_submit_button("Hesap Ekle"):
                new_acc = {
                    'id': str(random.randint(1000,9999)), 
                    'name': b_name, 
                    'balance': b_bal, 
                    'currency': b_curr,
                    'account_type': account_type
                }
                insert_account_db(new_acc)
                st.session_state.bank_accounts = load_bank_accounts_from_db()
                st.success("Hesap eklendi!")
                st.rerun()

    st.markdown(f"### {page_title} Listesi")
    
    # Filtrele: Sadece bu sayfanın tipine uygun hesapları göster
    filtered_accounts = [acc for acc in st.session_state.bank_accounts if acc['account_type'] == account_type]
    
    if not filtered_accounts:
        st.info(f"Kayıtlı {page_title} bulunamadı.")
    else:
        for acc in filtered_accounts:
            col_info, col_del = st.columns([4, 1])
            with col_info:
                st.markdown(f"<div class='bank-card'>💳 <strong>{acc['name']}</strong> - {acc['balance']:,.2f} {acc['currency']}</div>", unsafe_allow_html=True)
            with col_del:
                if st.button("Sil", key=f"del_{acc['id']}"):
                    delete_account_db(acc['id'])
                    st.session_state.bank_accounts = load_bank_accounts_from_db()
                    st.success("Hesap silindi!")
                    st.rerun()

# --- STATE YÖNETİMİ ---
if 'transactions' not in st.session_state or 'bank_accounts' not in st.session_state:
    init_db()
    trans_df = load_transactions_from_db()
    bank_list = load_bank_accounts_from_db()
    st.session_state.transactions = trans_df
    st.session_state.bank_accounts = bank_list

# --- SIDEBAR ---
with st.sidebar:
    st.title("Erdi K. 🤖")
    st.markdown("---")
    page = st.radio("Menü", [
        "Dashboard", 
        "İşlem Ekle", 
        "Banka Hesapları",
        "Kredi Kartları",
        "Nakit Paralar",
        "Yemek Kartları",
        "Ayarlar"
    ])
    st.markdown("---")

# --- PAGE: DASHBOARD ---
if page == "Dashboard":
    st.subheader("Finansal Genel Bakış")
    df = st.session_state.transactions
    
    col_filter1, col_filter2 = st.columns([3, 1])
    with col_filter1:
        months = ["Tüm Zamanlar"]
        if not df.empty:
            months += sorted(list(set(df['date'].dt.strftime('%Y-%m'))), reverse=True)
        selected_month = st.selectbox("Dönem Seçiniz", months)
    
    if selected_month != "Tüm Zamanlar":
        filtered_df = df[df['date'].dt.strftime('%Y-%m') == selected_month]
    else:
        filtered_df = df

    total_income = filtered_df[filtered_df['type'] == 'Income']['amount'].sum()
    total_expense = filtered_df[filtered_df['type'] == 'Expense']['amount'].sum()
    
    # Banka dahil TÜM varlıklar
    assets = get_total_assets()
    
    bank_names = [acc['name'] for acc in st.session_state.bank_accounts]
    
    # Net Worth hesaplama
    # Eğer bakiyeler otomatik güncelleniyorsa (güncelledik), aslında "Toplam Varlık" = get_total_assets().
    # Ancak "Toplam Varlık (Net)" kurgusu önceki koddaydı.
    # Artık her şey bir "Hesap" olduğu için, tüm hesapların toplamı Net Varlıktır.
    net_worth = assets

    c1, c2, c3 = st.columns([1, 1, 1])
    c1.metric("Toplam Varlık (Net)", f"₺{net_worth:,.2f}", "Tüm Hesaplar", delta_color="normal")
    c2.metric(f"{selected_month} Gelir", f"₺{total_income:,.2f}", f"+₺{total_income:,.2f}")
    c3.metric(f"{selected_month} Gider", f"₺{total_expense:,.2f}", f"-₺{total_expense:,.2f}", delta_color="inverse")

    st.markdown("---")

    row1 = st.columns(3)
    row2 = st.columns(3)
    colors = px.colors.qualitative.Pastel

    with row1[0]:
        pie_data = pd.DataFrame({'Label': ['Gelir', 'Gider'], 'Value': [total_income, total_expense]})
        fig = px.pie(pie_data, names='Label', values='Value', title='Gelir vs Gider', hole=0.0, color_discrete_sequence=['#22c55e', '#ef4444'])
        fig.update_traces(textfont=dict(size=14, color='white'), marker=dict(line=dict(color='#803811', width=0)))
        fig.update_layout(paper_bgcolor='#803811', plot_bgcolor='#803811', font=dict(color='white', size=14), title=dict(font=dict(size=16)), margin=dict(l=6,r=6,t=30,b=6))
        st.plotly_chart(fig, width='stretch', height=300)

    with row1[1]:
        exp_cat = filtered_df[filtered_df['type'] == 'Expense'].groupby('category')['amount'].sum().reset_index()
        fig = px.pie(exp_cat, names='category', values='amount', title='Gider Kategorileri', hole=0.5, color_discrete_sequence=colors)
        fig.update_traces(textfont=dict(size=14, color='white'))
        fig.update_layout(paper_bgcolor='#803811', plot_bgcolor='#803811', font=dict(color='white', size=14), title=dict(font=dict(size=16)), margin=dict(l=6,r=6,t=30,b=6))
        st.plotly_chart(fig, width='stretch', height=300)

    with row1[2]:
        savings = max(0, total_income - total_expense)
        sav_data = pd.DataFrame({'Label': ['Tasarruf', 'Harcama'], 'Value': [savings, total_expense]})
        fig = px.pie(sav_data, names='Label', values='Value', title='Tasarruf Oranı', hole=0.6, color_discrete_sequence=['#3b82f6', '#94a3b8'])
        fig.update_traces(textfont=dict(size=14, color='white'))
        fig.update_layout(paper_bgcolor='#803811', plot_bgcolor='#803811', font=dict(color='white', size=14), title=dict(font=dict(size=16)), margin=dict(l=6,r=6,t=30,b=6))
        st.plotly_chart(fig, width='stretch', height=300)

    with row2[0]:
        counts = filtered_df['type'].value_counts().reset_index(name='count')
        counts.columns = ['type', 'count']
        fig = px.pie(counts, names='type', values='count', title='İşlem Adetleri', color_discrete_sequence=['#ef4444', '#22c55e'])
        fig.update_traces(textfont=dict(size=14, color='white'))
        fig.update_layout(paper_bgcolor='#803811', plot_bgcolor='#803811', font=dict(color='white', size=14), title=dict(font=dict(size=16)), margin=dict(l=6,r=6,t=30,b=6))
        st.plotly_chart(fig, width='stretch', height=300)

    with row2[1]:
        top_exp = filtered_df[filtered_df['type'] == 'Expense'].nlargest(5, 'amount')
        fig = px.pie(top_exp, names='category', values='amount', title='En Büyük 5 Harcama', hole=0.4)
        fig.update_traces(textfont=dict(size=14, color='white'))
        fig.update_layout(paper_bgcolor='#803811', plot_bgcolor='#803811', font=dict(color='white', size=14), title=dict(font=dict(size=16)), margin=dict(l=6,r=6,t=30,b=6))
        st.plotly_chart(fig, width='stretch', height=300)

    with row2[2]:
        bank_df = pd.DataFrame(st.session_state.bank_accounts)
        if not bank_df.empty:
            bank_df['TRY_Value'] = bank_df.apply(lambda x: x['balance'] * 30 if x['currency'] == 'USD' else x['balance'], axis=1)
            fig = px.pie(bank_df, names='name', values='TRY_Value', title='Tüm Varlıklar Dağılımı', hole=0.5, color_discrete_sequence=px.colors.sequential.Plasma)
            fig.update_traces(textfont=dict(size=14, color='white'))
            fig.update_layout(paper_bgcolor='#803811', plot_bgcolor='#803811', font=dict(color='white', size=14), title=dict(font=dict(size=16)), margin=dict(l=6,r=6,t=30,b=6))
            st.plotly_chart(fig, width='stretch', height=300)

# --- PAGE: İŞLEM EKLE ---
elif page == "İşlem Ekle":
    st.subheader("Yeni Gelir veya Gider Ekle")
    
    if 'tx_type_selection' not in st.session_state:
        st.session_state.tx_type_selection = 'Income'

    editing_tx = st.session_state.get('editing_tx')
    if editing_tx:
        tx = get_transaction_by_id(editing_tx)
        if tx:
            st.session_state.tx_type_selection = tx['type']

    # TÜR SEÇİMİ
    col_type1, col_type2 = st.columns(2)
    with col_type1:
        if st.button("📉 GİDER", use_container_width=True, key="btn_expense_select"):
            st.session_state.tx_type_selection = 'Expense'
            st.rerun()
    
    with col_type2:
        if st.button("📈 GELİR", use_container_width=True, key="btn_income_select"):
            st.session_state.tx_type_selection = 'Income'
            st.rerun()

    sel_type = st.session_state.tx_type_selection
    if sel_type == 'Income':
        st.success(f"**Seçilen:** :green[+ GELİR]", icon="🟢")
    else:
        st.error(f"**Seçilen:** :red[- GİDER]", icon="🔴")
    
    st.markdown("---")

    # DÜZENLEME
    if editing_tx:
        tx = get_transaction_by_id(editing_tx)
        if not tx:
            st.error("Düzenlenecek işlem bulunamadı.")
            st.session_state.pop('editing_tx', None)
        else:
            with st.form("edit_transaction_form"):
                t_type = st.session_state.tx_type_selection 
                col1, col2 = st.columns(2)
                with col1:
                    amount = st.number_input("Tutar", min_value=0.01, value=float(tx['amount']), format="%.2f")
                with col2:
                    date = st.date_input("Tarih", pd.to_datetime(tx['date']).date())
                
                payment_methods = get_payment_methods()
                current_pm = tx.get('payment_method')
                if current_pm not in payment_methods:
                    payment_methods.append(current_pm)
                
                payment_method = st.selectbox("Ödeme Yöntemi / Kaynak", payment_methods, index=payment_methods.index(current_pm))
                
                categories = get_transaction_categories()
                category = st.selectbox("Kategori", categories, index=categories.index(tx['category']) if tx['category'] in categories else 0)

                desc = st.text_area("Açıklama", tx.get('description',''))
                
                col_ok, col_cancel = st.columns([1,1])
                with col_ok:
                    if st.form_submit_button("Güncelle"):
                        try:
                            update_transaction_db(editing_tx, t_type, amount, category, date, desc, payment_method)
                            st.session_state.transactions = load_transactions_from_db()
                            st.success("İşlem ve bakiye güncellendi!")
                            st.session_state.pop('editing_tx', None)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Güncelleme hatası: {e}")
                with col_cancel:
                    if st.form_submit_button("İptal", key="cancel_edit"):
                        st.session_state.pop('editing_tx', None)
                        st.rerun()

    # YENİ EKLEME
    if not st.session_state.get('editing_tx'):
        with st.form("transaction_form"):
            t_type = st.session_state.tx_type_selection
            col1, col2 = st.columns(2)
            with col1:
                amount = st.number_input("Tutar", min_value=0.01, format="%.2f")
            with col2:
                date = st.date_input("Tarih", datetime.date.today())
            
            payment_methods = get_payment_methods()
            payment_method = st.selectbox("Ödeme Yöntemi / Kaynak", payment_methods, index=0)
            
            categories = get_transaction_categories()
            default_idx = 0 
            if t_type == 'Expense':
                default_idx = 3
            
            category = st.selectbox("Kategori", categories, index=default_idx)

            desc = st.text_area("Açıklama")
            submitted = st.form_submit_button("Kaydet")

            if submitted:
                add_transaction(t_type, amount, category, date, desc, payment_method)
                st.success("İşlem başarıyla eklendi!")

    st.markdown("---")

    # LİSTELEME
    st.markdown("### Mevcut İşlemler")
    tx_df = st.session_state.transactions.sort_values('date', ascending=False).reset_index(drop=True)

    # Filtreler
    if 'tx_filter_type' not in st.session_state:
        st.session_state['tx_filter_type'] = 'Tümü'
    if 'tx_filter_cat' not in st.session_state:
        st.session_state['tx_filter_cat'] = 'Tümü'
    if 'tx_filter_search' not in st.session_state:
        st.session_state['tx_filter_search'] = ''
    if 'tx_filter_min_date' not in st.session_state:
        st.session_state['tx_filter_min_date'] = tx_df['date'].min().date() if not tx_df.empty else datetime.date.today()
    if 'tx_filter_max_date' not in st.session_state:
        st.session_state['tx_filter_max_date'] = tx_df['date'].max().date() if not tx_df.empty else datetime.date.today()

    with st.expander("Filtreler", expanded=False):
        col_type, col_min, col_max, col_cat, col_search, col_clear = st.columns([1,1,1,1,2,0.6])
        with col_type:
            st.selectbox("Tür", ["Tümü", "Gelir", "Gider"], key='tx_filter_type', format_func=lambda x: 'Income' if x=='Gelir' else ('Expense' if x=='Gider' else x))
        with col_min:
            st.date_input("Başlangıç", key='tx_filter_min_date')
        with col_max:
            st.date_input("Bitiş", key='tx_filter_max_date')
        with col_cat:
            categories = ["Tümü"] + get_transaction_categories()
            st.selectbox("Kategori", categories, key='tx_filter_cat')
        with col_search:
            st.text_input("Ara", key='tx_filter_search', placeholder="Örn: market, maaş")
        with col_clear:
            st.write("")
            if st.button("Temizle", key="clear_filters"):
                st.session_state.pop('tx_filter_type', None)
                st.session_state.pop('tx_filter_cat', None)
                st.session_state.pop('tx_filter_search', None)
                st.session_state.pop('tx_filter_min_date', None)
                st.session_state.pop('tx_filter_max_date', None)
                st.rerun()

    tx_filtered = tx_df.copy()
    tf_type = st.session_state.get('tx_filter_type')
    if tf_type and tf_type != 'Tümü':
        db_type = 'Income' if tf_type == 'Gelir' else 'Expense'
        tx_filtered = tx_filtered[tx_filtered['type'] == db_type]
    try:
        min_d = pd.to_datetime(st.session_state['tx_filter_min_date'])
        max_d = pd.to_datetime(st.session_state['tx_filter_max_date'])
        tx_filtered = tx_filtered[(tx_filtered['date'] >= min_d) & (tx_filtered['date'] <= max_d)]
    except Exception:
        pass
    if st.session_state.get('tx_filter_cat') and st.session_state['tx_filter_cat'] != 'Tümü':
        tx_filtered = tx_filtered[tx_filtered['category'] == st.session_state['tx_filter_cat']]
    q = st.session_state.get('tx_filter_search','').strip().lower()
    if q:
        tx_filtered = tx_filtered[tx_filtered['category'].fillna('').str.lower().str.contains(q) | 
                                  tx_filtered['description'].fillna('').str.lower().str.contains(q) |
                                  tx_filtered['payment_method'].fillna('').str.lower().str.contains(q)]

    st.write(f"Sonuç: **{len(tx_filtered)}** işlem gösteriliyor")

    if tx_filtered.empty:
        st.info("Filtrelere uygun işlem bulunamadı.")
    else:
        h1, h2, h3, h4, h5, h6 = st.columns([1,1,2,1,2,2])
        h1.markdown("**Tarih**")
        h2.markdown("**Tür**")
        h3.markdown("**Kategori**")
        h4.markdown("**Tutar**")
        h5.markdown("**Yöntem**")
        h6.markdown("**Aksiyon**")

        for _, row in tx_filtered.iterrows():
            c1, c2, c3, c4, c5, c6 = st.columns([1,1,2,1,2,2])
            date_str = pd.to_datetime(row['date']).date()
            c1.markdown(f"<div style='font-size:14px; font-weight:600; font-family: system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial;'>{date_str}</div>", unsafe_allow_html=True)
            
            display_type = "GELİR" if row['type'] == 'Income' else "GİDER"
            c2.markdown(f"<span style='color: {'#22c55e' if row['type'] == 'Income' else '#ef4444'}; font-weight:bold;'>{display_type}</span>", unsafe_allow_html=True)
            
            c3.write(row['category'])
            c4.write(f"{row['amount']:,.2f}")
            
            p_method = row.get('payment_method', '-')
            c5.write(p_method)

            row_id_str = str(row['id'])
            btn_edit_col, btn_del_col = c6.columns([1,1])
            if btn_edit_col.button("Düzenle", key=f"edit_{row_id_str}"):
                st.session_state['editing_tx'] = row_id_str
                st.rerun()

            if btn_del_col.button("Sil", key=f"del_{row_id_str}"):
                st.session_state[f'confirm_del_{row_id_str}'] = True
                st.rerun()

            if st.session_state.get(f'confirm_del_{row_id_str}'):
                with st.expander("Silme Onayı", expanded=True):
                    st.warning("Bu işlemi silmek istediğinize emin misiniz?")
                    col_yes, col_no = st.columns([1,1])
                    if col_yes.button("Evet, Sil", key=f"confirm_yes_{row_id_str}"):
                        try:
                            delete_transaction_db(row_id_str)
                            st.session_state.transactions = load_transactions_from_db()
                            st.success("İşlem silindi ve bakiye düzeltildi.")
                            st.session_state.pop(f'confirm_del_{row_id_str}', None)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Silme hatası: {e}")
                    if col_no.button("İptal", key=f"confirm_no_{row_id_str}"):
                        st.session_state.pop(f'confirm_del_{row_id_str}', None)
                        st.rerun()
            st.markdown("<hr style='margin:2px 0; border:none; border-top:1px solid rgba(0,0,0,0.1);'/>", unsafe_allow_html=True)

# --- SAYFALAR: BANKA, KREDİ KARTI, NAKİT, YEMEK KARTI ---
elif page == "Banka Hesapları":
    render_account_manager("Banka Hesaplarım", "Banka")
elif page == "Kredi Kartları":
    render_account_manager("Kredi Kartlarım", "Kredi Kartı")
elif page == "Nakit Paralar":
    render_account_manager("Nakit Paralarım", "Nakit")
elif page == "Yemek Kartları":
    render_account_manager("Yemek Kartlarım", "Yemek Kartı")

# --- SAYFA: AYARLAR ---
elif page == "Ayarlar":
    st.subheader("Uygulama Ayarları")
    
    col1, col2 = st.columns(2)
    with col1:
        st.warning("Verileri Sıfırla")
        if st.button("Bütün Verileri Temizle", key="request_clear"):
            st.session_state['confirm_clear'] = True
            st.rerun()

        if st.session_state.get('confirm_clear'):
            with st.expander("Onayla", expanded=True):
                st.warning("Bu işlem geri alınamaz. Tüm verileri silmek istediğinize emin misiniz?")
                col_yes, col_no = st.columns([1,1])
                if col_yes.button("Evet, Sil", key="confirm_yes_clear"):
                    clear_db()
                    st.session_state.transactions = load_transactions_from_db()
                    st.session_state.bank_accounts = load_bank_accounts_from_db()
                    st.success("Veriler temizlendi.")
                    st.session_state.pop('confirm_clear', None)
                    st.rerun()
                if col_no.button("İptal", key="confirm_no_clear"):
                    st.session_state.pop('confirm_clear', None)
                    st.info("İşlem iptal edildi.")
                    st.rerun()
            
    with col2:
        st.info("Tema Ayarı")
        st.write("Streamlit temasını değiştirmek için sağ üstteki 'Settings' menüsünü kullanabilirsiniz (Dark/Light Mode).")
        with st.expander("DB Durumu (Debug)"):
            st.write(f"DB dosyası: `{DB_PATH}`")
            try:
                tx = load_transactions_from_db()
                ba = load_bank_accounts_from_db()
                st.write(f"Toplam İşlem (DB): {len(tx)}")
                st.write(f"Toplam Hesap (DB): {len(ba)}")
                if not tx.empty:
                    st.write("Son 5 işlem:")
                    st.dataframe(tx.head(5))
                if ba:
                    st.write("Tüm Hesaplar (DB):")
                    st.json(ba)
            except Exception as e:
                st.error(f"DB okunamadı: {e}")