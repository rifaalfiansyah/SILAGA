import os
import uuid
import io
from datetime import datetime, date
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, Response, send_file
)

from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from fpdf import FPDF

from database import get_connection
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY')

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'loggedin_rifa' not in session:
                return redirect(url_for('login'))
            if session.get('role_rifa') != role:
                flash('Akses ditolak! Anda tidak memiliki izin untuk halaman ini.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def role_required_either(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'loggedin_rifa' not in session:
                return redirect(url_for('login'))
            if session.get('role_rifa') not in roles:
                flash('Anda tidak memiliki akses ke halaman ini.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def warga_lokal_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        nik_user = session.get('nik_rifa')
        
        conn_rifa = get_connection()
        cursor_rifa = conn_rifa.cursor(dictionary=True)
        
        cursor_rifa.execute("SELECT no_kk_rifa FROM penduduk_rifa WHERE nik_rifa = %s", (nik_user,))
        data_penduduk = cursor_rifa.fetchone()
        
        cursor_rifa.close()
        conn_rifa.close()
        
        if not data_penduduk or not data_penduduk['no_kk_rifa']:
            flash('Akses ditolak! Fitur ini khusus untuk warga asli yang memiliki Kartu Keluarga (KK) lokal. Pendatang hanya dapat mengajukan Izin Tinggal.', 'warning')
            return redirect(url_for('dashboard_masyarakat'))
            
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'loggedin_rifa' in session:
        role_rifa = session.get('role_rifa')
        
        if role_rifa == 'masyarakat':
            return redirect(url_for('dashboard_masyarakat'))
        elif role_rifa == 'petugas':
            return redirect(url_for('dashboard_petugas'))
        elif role_rifa == 'admin':
            return redirect(url_for('dashboard_admin'))
        else:
            session.clear()
            flash('Gagal masuk: Akun Anda tidak memiliki Role yang valid. Silakan daftar ulang.', 'danger')
            return redirect(url_for('login'))

    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'loggedin_rifa' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        nik_rifa = request.form['nik_rifa']
        password_rifa = request.form['password_rifa']

        conn_rifa = get_connection()
        cursor_rifa = conn_rifa.cursor(dictionary=True)

        query_rifa = """
            SELECT u.*, p.nama_lengkap_rifa 
            FROM user_rifa u
            JOIN penduduk_rifa p ON u.nik_penduduk_rifa = p.nik_rifa
            WHERE u.nik_penduduk_rifa = %s AND u.status_aktif_rifa = 1
        """
        cursor_rifa.execute(query_rifa, (nik_rifa,))
        user_rifa = cursor_rifa.fetchone()
        cursor_rifa.close()
        conn_rifa.close()

        if user_rifa and check_password_hash(user_rifa['password_rifa'], password_rifa):
            session['loggedin_rifa'] = True
            session['id_user_rifa'] = user_rifa['id_user_rifa']
            session['nama_lengkap_rifa'] = user_rifa['nama_lengkap_rifa']
            session['nik_rifa'] = user_rifa['nik_penduduk_rifa']
            session['role_rifa'] = user_rifa['role_rifa'].lower()
            
            flash(f"Selamat datang kembali, {user_rifa['nama_lengkap_rifa']}!", 'success')
            return redirect(url_for('index'))
        
        flash('NIK atau Password salah!', 'danger')
    return render_template('login.html')

@app.route('/daftar', methods=['GET', 'POST'])
def daftar():
    if request.method == 'POST':
        nik_rifa = request.form['nik_rifa']
        nama_lengkap_rifa = request.form.get('nama_lengkap_rifa')
        tanggal_lahir_rifa = request.form.get('tanggal_lahir_rifa')
        tempat_lahir_rifa = request.form.get('tempat_lahir_rifa')
        email_rifa = request.form['email_rifa']
        no_telp_rifa = request.form['no_telp_rifa']
        password_rifa = request.form['password_rifa']
        hashed_password_rifa = generate_password_hash(password_rifa)

        conn_rifa = get_connection()
        cursor_rifa = conn_rifa.cursor(dictionary=True)

        try:
            cursor_rifa.execute("SELECT * FROM user_rifa WHERE nik_penduduk_rifa = %s", (nik_rifa,))
            if cursor_rifa.fetchone():
                flash('NIK ini sudah memiliki akun!', 'warning')
                return redirect(url_for('login'))

            cursor_rifa.execute("SELECT * FROM penduduk_rifa WHERE nik_rifa = %s", (nik_rifa,))
            penduduk = cursor_rifa.fetchone()
            
            if not penduduk:
                if not nama_lengkap_rifa or nama_lengkap_rifa.strip() == '':
                    flash('Pendaftar baru/pendatang wajib mengisi Nama Lengkap di form pendaftaran!', 'danger')
                    return redirect(url_for('daftar'))

                if not tanggal_lahir_rifa:
                    tanggal_lahir_rifa = '1970-01-01'
                
                if not tempat_lahir_rifa:
                    tempat_lahir_rifa = '-'

                query_pendatang = """
                    INSERT INTO penduduk_rifa (
                        nik_rifa, no_kk_rifa, nama_lengkap_rifa, tempat_lahir_rifa, 
                        tanggal_lahir_rifa, jenis_kelamin_rifa, agama_rifa, pendidikan_rifa, 
                        pekerjaan_rifa, status_perkawinan_rifa, kewarganegaraan_rifa, status_hidup_rifa
                    ) VALUES (%s, NULL, %s, %s, %s, 'L', '-', '-', '-', 'Belum Kawin', 'WNI', 'Hidup')
                """
                cursor_rifa.execute(query_pendatang, (nik_rifa, nama_lengkap_rifa, tempat_lahir_rifa, tanggal_lahir_rifa))

            cursor_rifa.execute("""
                INSERT INTO user_rifa (nik_penduduk_rifa, email_rifa, password_rifa, no_telp_rifa, role_rifa, status_aktif_rifa) 
                VALUES (%s, %s, %s, %s, 'masyarakat', 1)
            """, (nik_rifa, email_rifa, hashed_password_rifa, no_telp_rifa))
            
            conn_rifa.commit()
            flash('Registrasi berhasil! Jika Anda pendatang, silakan ajukan Izin Tinggal.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            conn_rifa.rollback()
            flash(f'Terjadi kesalahan: {str(e)}', 'danger')
        finally:
            cursor_rifa.close()
            conn_rifa.close()

    return render_template('daftar.html')   

# Masyarakat

@app.route('/masyarakat/dashboard')
@role_required('masyarakat')
def dashboard_masyarakat():
    id_user_rifa = session.get('id_user_rifa')
    
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)

    try:
        query_rifa = """
            SELECT 'Akta Kematian' as jenis_layanan, tanggal_pengajuan_rifa, status_pengajuan_rifa, id_akta_kematian_rifa as id_p
            FROM akta_kematian_rifa 
            WHERE id_user_rifa = %s
            
            UNION ALL
            
            SELECT 'Surat Pindah' as jenis_layanan, tanggal_pengajuan_rifa, status_pengajuan_rifa, id_surat_pindah_rifa as id_p
            FROM surat_pindah_rifa 
            WHERE id_user_rifa = %s
            
            UNION ALL
            
            SELECT 'Izin Tinggal' as jenis_layanan, tanggal_pengajuan_rifa, status_pengajuan_rifa, id_izin_tinggal_rifa as id_p
            FROM izin_tinggal_rifa 
            WHERE id_user_rifa = %s
            
            ORDER BY tanggal_pengajuan_rifa DESC
        """
        cursor_rifa.execute(query_rifa, (id_user_rifa, id_user_rifa, id_user_rifa))
        data_pengajuan_rifa = cursor_rifa.fetchall()
        
        total_pengajuan = len(data_pengajuan_rifa)
        total_akta = sum(1 for item in data_pengajuan_rifa if item['jenis_layanan'] == 'Akta Kematian')
        total_pindah = sum(1 for item in data_pengajuan_rifa if item['jenis_layanan'] == 'Surat Pindah')
        total_izin = sum(1 for item in data_pengajuan_rifa if item['jenis_layanan'] == 'Izin Tinggal')
        
        return render_template('masyarakat/dashboard.html', 
                               data_pengajuan=data_pengajuan_rifa, 
                               total_pengajuan=total_pengajuan,
                               total_akta=total_akta,
                               total_pindah=total_pindah,
                               total_izin=total_izin,
                               nama_rifa=session.get('nama_lengkap_rifa'))

    except Exception as e:
        print("Error Dashboard Masyarakat:", str(e))
        return f"Terjadi kesalahan database: {str(e)}"
    finally:
        if 'cursor_rifa' in locals(): cursor_rifa.close()
        if 'conn_rifa' in locals(): conn_rifa.close()

@app.route('/masyarakat/daftar-pengajuan')
@role_required('masyarakat')
def daftar_pengajuan_masyarakat():
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    cursor_rifa.execute("SELECT no_kk_rifa FROM penduduk_rifa WHERE nik_rifa = %s", (session['nik_rifa'],))
    data = cursor_rifa.fetchone()
    cursor_rifa.close()
    conn_rifa.close()
    
    punya_kk = True if (data and data['no_kk_rifa']) else False

    return render_template('masyarakat/daftar-pengajuan.html', punya_kk=punya_kk)

@app.route('/masyarakat/profile')
@role_required('masyarakat')
def profile_masyarakat():
    nik_rifa = session['nik_rifa']
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)

    cursor_rifa.execute("""
        SELECT p.*, u.*, kk.*
        FROM penduduk_rifa p 
        JOIN user_rifa u ON p.nik_rifa = u.nik_penduduk_rifa
        LEFT JOIN kartu_keluarga_rifa kk ON p.no_kk_rifa = kk.no_kk_rifa
        WHERE p.nik_rifa = %s
    """, (nik_rifa,))
    data_user_rifa = cursor_rifa.fetchone()
    
    cursor_rifa.close()
    conn_rifa.close()
    return render_template('masyarakat/profile.html', user=data_user_rifa)

# Pengajuan Akta Kematian

@app.route('/masyarakat/pengajuan/akta-kematian', methods=['GET'])
@role_required('masyarakat')
@warga_lokal_required
def pengajuan_akta_kematian_page():
    return render_template('masyarakat/pengajuan/akta_kematian.html', 
                           nama_rifa=session.get('nama_lengkap_rifa'))

@app.route('/masyarakat/pengajuan/akta-kematian/proses', methods=['POST'])
@role_required('masyarakat')
@warga_lokal_required
def pengajuan_akta_kematian_proses():
    id_user_rifa = session['id_user_rifa']
    nik_pemohon_rifa = session['nik_rifa']

    nik_jenazah_rifa = request.form.get('nik_jenazah_rifa')
    tanggal_wafat_rifa = request.form.get('tanggal_meninggal_rifa')
    tempat_wafat_rifa = request.form.get('tempat_meninggal_rifa')
    sebab_wafat_rifa = request.form.get('sebab_meninggal_rifa')
    hubungan_rifa = request.form.get('hubungan_pemohon_rifa')
    keterangan_rifa = request.form.get('keterangan_pemohon_rifa')

    nik_s1 = request.form.get('nik_saksi_1_rifa')
    nama_s1 = request.form.get('nama_saksi_1_rifa')
    nik_s2 = request.form.get('nik_saksi_2_rifa')
    nama_s2 = request.form.get('nama_saksi_2_rifa')

    def save_file(file_obj, prefix):
        if file_obj and file_obj.filename != '':
            ext = os.path.splitext(file_obj.filename)[1]
            
            kode_unik = uuid.uuid4().hex[:8]
            
            filename = secure_filename(f"{prefix}_{nik_jenazah_rifa}_{kode_unik}{ext}")
            
            file_obj.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return filename
        return None

    try:
        # Berkas Jenazah
        f_ktp_j = save_file(request.files.get('file_ktp_jenazah_rifa'), "KTP_JNZ")
        f_kk = save_file(request.files.get('file_kk_rifa'), "KK")
        f_surat_m = save_file(request.files.get('file_surat_kematian_rifa'), "SRT_MATI")

        # Berkas Saksi
        f_ktp_s1 = save_file(request.files.get('file_ktp_saksi_1_rifa'), "KTP_S1")
        f_ktp_s2 = save_file(request.files.get('file_ktp_saksi_2_rifa'), "KTP_S2")

        conn_rifa = get_connection()
        cursor_rifa = conn_rifa.cursor()

        cursor_rifa.execute("""
          SELECT id_akta_kematian_rifa FROM akta_kematian_rifa
          WHERE nik_jenazah_rifa = %s AND status_pengajuan_rifa = 'disetujui'
        """, (nik_jenazah_rifa,))
        if cursor_rifa.fetchone():
            flash('Akta kematian untuk NIK ini sudah disetujui.', 'warning')
            return redirect(url_for('dashboard_masyarakat'))

        query_akta = """
            INSERT INTO akta_kematian_rifa (
                nik_jenazah_rifa, nik_pemohon_rifa, id_user_rifa, 
                tanggal_meninggal_rifa, tempat_meninggal_rifa, sebab_meninggal_rifa, hubungan_pemohon_rifa, keterangan_pemohon_rifa,
                file_ktp_jenazah_rifa, file_kk_rifa, file_surat_kematian_rifa, 
                status_pengajuan_rifa, tanggal_pengajuan_rifa
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'menunggu', NOW())
        """
        cursor_rifa.execute(query_akta, (
            nik_jenazah_rifa, nik_pemohon_rifa, id_user_rifa,
            tanggal_wafat_rifa, tempat_wafat_rifa, sebab_wafat_rifa, hubungan_rifa, keterangan_rifa,
            f_ktp_j, f_kk, f_surat_m
        ))

        id_akta_baru = cursor_rifa.lastrowid

        query_saksi = """
            INSERT INTO saksi_akta_kematian_rifa (
                id_akta_kematian_rifa, 
                nik_saksi_1_rifa, nama_saksi_1_rifa, file_ktp_saksi_1_rifa,
                nik_saksi_2_rifa, nama_saksi_2_rifa, file_ktp_saksi_2_rifa
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor_rifa.execute(query_saksi, (
            id_akta_baru, 
            nik_s1, nama_s1, f_ktp_s1, 
            nik_s2, nama_s2, f_ktp_s2
        ))

        conn_rifa.commit()
        flash('Pengajuan Akta Kematian dan data Saksi berhasil dikirim!', 'success')
        return redirect(url_for('dashboard_masyarakat'))

    except Exception as e:
        if 'conn_rifa' in locals():
            conn_rifa.rollback()
        print(f"Error Pengajuan: {str(e)}")
        flash(f'Terjadi kesalahan: {str(e)}', 'danger')
        return redirect(url_for('index'))
    finally:
        if 'cursor_rifa' in locals(): cursor_rifa.close()
        if 'conn_rifa' in locals(): conn_rifa.close()

@app.route('/masyarakat/detail/detail_akta/<int:id_p>')
@role_required('masyarakat')
def detail_pengajuan_masyarakat(id_p):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    
    try:
        query_akta = """
            SELECT a.*, p.nama_lengkap_rifa AS nama_jenazah,
                    s.nik_saksi_1_rifa, s.nama_saksi_1_rifa, s.file_ktp_saksi_1_rifa, 
                    s.nik_saksi_2_rifa, s.nama_saksi_2_rifa, s.file_ktp_saksi_2_rifa 
            FROM akta_kematian_rifa a
            JOIN penduduk_rifa p ON a.nik_jenazah_rifa = p.nik_rifa
            LEFT JOIN saksi_akta_kematian_rifa s ON a.id_akta_kematian_rifa = s.id_akta_kematian_rifa
            WHERE a.id_akta_kematian_rifa = %s AND a.id_user_rifa = %s
        """
        cursor_rifa.execute(query_akta, (id_p, session['id_user_rifa']))
        data = cursor_rifa.fetchone()

        return render_template('masyarakat/detail_akta.html', data=data)


    except Exception as e:
        print(f"Error Detail: {str(e)}")
        return "Terjadi kesalahan."
    finally:
        cursor_rifa.close()
        conn_rifa.close()

# Pengajuan Surat Pindah

@app.route('/masyarakat/pengajuan/surat-pindah', methods=['GET'])
@role_required('masyarakat')
@warga_lokal_required
def pengajuan_surat_pindah_page():
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    
    cursor_rifa.execute("SELECT * FROM kelurahan_rifa ORDER BY nama_kelurahan_rifa ASC")
    daftar_kelurahan = cursor_rifa.fetchall()
    
    cursor_rifa.close()
    conn_rifa.close()
    
    return render_template('masyarakat/pengajuan/surat_pindah.html', 
                           daftar_kelurahan=daftar_kelurahan,
                           nama_rifa=session.get('nama_lengkap_rifa'))

@app.route('/masyarakat/pengajuan/surat-pindah/proses', methods=['POST'])
@role_required('masyarakat')
@warga_lokal_required
def pengajuan_surat_pindah_proses():
    id_user_rifa = session['id_user_rifa']
    nik_pemohon_rifa = session['nik_rifa']

    tanggal_pindah_rifa = request.form.get('tanggal_pindah_rifa')
    alasan_pindah_rifa = request.form.get('alasan_pindah_rifa')
    status_keluarga_rifa = request.form.get('status_keluarga_rifa')
    alamat_asal_rifa = request.form.get('alamat_asal_rifa')
    alamat_tujuan_rifa = request.form.get('alamat_tujuan_rifa')
    id_kelurahan_rifa = request.form.get('id_kelurahan_rifa')

    if id_kelurahan_rifa == 'LUAR_WILAYAH':
        id_kelurahan_rifa = None

    nik_anggota_list = request.form.getlist('nik_anggota_rifa[]')
    status_anggota_list = request.form.getlist('status_anggota_rifa[]')

    def save_file(file_obj, prefix, identifier):
        if file_obj and file_obj.filename != '':
            ext = os.path.splitext(file_obj.filename)[1]
            
            kode_unik = uuid.uuid4().hex[:8]
            
            filename = secure_filename(f"{prefix}_{identifier}_{kode_unik}{ext}")
            
            file_obj.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return filename
        return None

    try:
        f_kk = save_file(request.files.get('file_kk_rifa'), "KK_PINDAH", nik_pemohon_rifa)
        f_ktp_pemohon = save_file(request.files.get('file_ktp_pemohon_rifa'), "KTP_P_PINDAH", nik_pemohon_rifa)

        conn_rifa = get_connection()
        cursor_rifa = conn_rifa.cursor()

        query_pindah = """
            INSERT INTO surat_pindah_rifa (
                nik_rifa, id_user_rifa, id_kelurahan_rifa, 
                tanggal_pindah_rifa, alasan_pindah_rifa, status_keluarga_rifa, 
                alamat_asal_rifa, alamat_tujuan_rifa, 
                file_kk_rifa, file_ktp_pemohon_rifa, 
                status_pengajuan_rifa, tanggal_pengajuan_rifa
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'menunggu', NOW())
        """
        cursor_rifa.execute(query_pindah, (
            nik_pemohon_rifa, id_user_rifa, id_kelurahan_rifa,
            tanggal_pindah_rifa, alasan_pindah_rifa, status_keluarga_rifa,
            alamat_asal_rifa, alamat_tujuan_rifa,
            f_kk, f_ktp_pemohon
        ))

        id_surat_pindah_baru = cursor_rifa.lastrowid

        query_anggota = """
            INSERT INTO anggota_pindah_rifa (
                id_surat_pindah_rifa, nik_rifa, status_keluarga_rifa
            ) VALUES (%s, %s, %s)
        """
        
        if nik_anggota_list and len(nik_anggota_list) > 0 and nik_anggota_list[0] != "":
            for i in range(len(nik_anggota_list)):
                nik_a = nik_anggota_list[i]
                status_a = status_anggota_list[i]
                
                cursor_rifa.execute(query_anggota, (id_surat_pindah_baru, nik_a, status_a))

        conn_rifa.commit()
        flash('Pengajuan Surat Pindah berhasil dikirim!', 'success')
        return redirect(url_for('dashboard_masyarakat'))

    except Exception as e:
        if 'conn_rifa' in locals():
            conn_rifa.rollback()
        print(f"Error Pengajuan Surat Pindah: {str(e)}")
        flash(f'Terjadi kesalahan: {str(e)}', 'danger')
        return redirect(url_for('pengajuan_surat_pindah_page'))
    finally:
        if 'cursor_rifa' in locals(): cursor_rifa.close()
        if 'conn_rifa' in locals(): conn_rifa.close()

@app.route('/masyarakat/detail-pindah/<int:id_p>')
@role_required('masyarakat')
def detail_pindah_masyarakat(id_p):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    
    try:
        query_pindah = """
            SELECT s.*, p.nama_lengkap_rifa AS nama_pemohon, k.nama_kelurahan_rifa
            FROM surat_pindah_rifa s
            JOIN penduduk_rifa p ON s.nik_rifa = p.nik_rifa
            LEFT JOIN kelurahan_rifa k ON s.id_kelurahan_rifa = k.id_kelurahan_rifa
            WHERE s.id_surat_pindah_rifa = %s AND s.id_user_rifa = %s
        """
        cursor_rifa.execute(query_pindah, (id_p, session['id_user_rifa']))
        data = cursor_rifa.fetchone()

        if not data:
            flash("Data tidak ditemukan!", "danger")
            return redirect(url_for('dashboard_masyarakat'))

        query_anggota = "SELECT * FROM anggota_pindah_rifa WHERE id_surat_pindah_rifa = %s"
        cursor_rifa.execute(query_anggota, (id_p,))
        anggota = cursor_rifa.fetchall()

        return render_template('masyarakat/detail_pindah.html', data=data, anggota=anggota)
    finally:
        cursor_rifa.close()
        conn_rifa.close()

# Pengajuan Izin Tinggal

@app.route('/masyarakat/pengajuan/izin-tinggal', methods=['GET'])
@role_required('masyarakat')
def pengajuan_izin_tinggal_page():
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    
    cursor_rifa.execute("SELECT * FROM kelurahan_rifa ORDER BY nama_kelurahan_rifa ASC")
    daftar_kelurahan = cursor_rifa.fetchall()
    
    cursor_rifa.close()
    conn_rifa.close()
    
    return render_template('masyarakat/pengajuan/izin_tinggal.html', 
                           daftar_kelurahan=daftar_kelurahan,
                           nama_rifa=session.get('nama_lengkap_rifa'))

@app.route('/masyarakat/pengajuan/izin-tinggal/proses', methods=['POST'])
@role_required('masyarakat')
def pengajuan_izin_tinggal_proses():
    id_user_rifa = session['id_user_rifa']
    nik_pemohon_rifa = session['nik_rifa']

    id_kelurahan_rifa = request.form.get('id_kelurahan_rifa')
    alamat_asal_rifa = request.form.get('alamat_asal_rifa') 
    alamat_tujuan_rifa = request.form.get('alamat_tujuan_rifa')
    tanggal_mulai_rifa = request.form.get('tanggal_mulai_rifa')
    tanggal_berakhir_rifa = request.form.get('tanggal_berakhir_rifa')
    keterangan_rifa = request.form.get('keterangan_rifa')

    def save_file(file_obj, prefix):
        if file_obj and file_obj.filename != '':
            ext = os.path.splitext(file_obj.filename)[1]
            kode_unik = uuid.uuid4().hex[:8]
            filename = secure_filename(f"{prefix}_{nik_pemohon_rifa}_{kode_unik}{ext}")
            file_obj.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            return filename
        return None

    try:
        f_ktp = save_file(request.files.get('file_ktp_rifa'), "KTP_IZIN")
        f_kk = save_file(request.files.get('file_kk_rifa'), "KK_IZIN")

        conn_rifa = get_connection()
        cursor_rifa = conn_rifa.cursor()

        query_izin = """
            INSERT INTO izin_tinggal_rifa (
                nik_pemohon_rifa, id_user_rifa, id_kelurahan_rifa, 
                alamat_asal_rifa, alamat_tujuan_rifa, keterangan_rifa, 
                tanggal_mulai_rifa, tanggal_berakhir_rifa,
                file_ktp_rifa, file_kk_rifa, 
                status_pengajuan_rifa, tanggal_pengajuan_rifa
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'menunggu', NOW())
        """
        
        cursor_rifa.execute(query_izin, (
            nik_pemohon_rifa, id_user_rifa, id_kelurahan_rifa,
            alamat_asal_rifa, alamat_tujuan_rifa, keterangan_rifa,
            tanggal_mulai_rifa, tanggal_berakhir_rifa,
            f_ktp, f_kk
        ))

        conn_rifa.commit()
        flash('Pengajuan Izin Tinggal berhasil dikirim!', 'success')
        return redirect(url_for('dashboard_masyarakat'))

    except Exception as e:
        if 'conn_rifa' in locals(): conn_rifa.rollback()
        flash(f'Terjadi kesalahan: {str(e)}', 'danger')
        return redirect(url_for('pengajuan_izin_tinggal_page'))
    finally:
        if 'cursor_rifa' in locals(): cursor_rifa.close()
        if 'conn_rifa' in locals(): conn_rifa.close()

@app.route('/masyarakat/detail-izin/<int:id_p>')
@role_required('masyarakat')
def detail_izin_masyarakat(id_p):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    
    try:
        query_izin = """
            SELECT i.*, p.nama_lengkap_rifa AS nama_pemohon, k.nama_kelurahan_rifa 
            FROM izin_tinggal_rifa i
            JOIN penduduk_rifa p ON i.nik_pemohon_rifa = p.nik_rifa
            LEFT JOIN kelurahan_rifa k ON i.id_kelurahan_rifa = k.id_kelurahan_rifa
            WHERE i.id_izin_tinggal_rifa = %s AND i.id_user_rifa = %s
        """
        cursor_rifa.execute(query_izin, (id_p, session['id_user_rifa']))
        data = cursor_rifa.fetchone()

        if not data:
            flash("Data pengajuan tidak ditemukan!", "danger")
            return redirect(url_for('dashboard_masyarakat'))

        return render_template('masyarakat/detail_izin.html', data=data)
    finally:
        cursor_rifa.close()
        conn_rifa.close()

# Admin

@app.route('/admin/dashboard')
@role_required('admin')
def dashboard_admin():
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)

    cursor_rifa.execute("SELECT COUNT(*) as total FROM user_rifa")
    total_user_rifa = cursor_rifa.fetchone()['total']

    cursor_rifa.execute("SELECT COUNT(*) as total FROM penduduk_rifa")
    total_penduduk_rifa = cursor_rifa.fetchone()['total']

    cursor_rifa.execute("SELECT COUNT(*) as total FROM kartu_keluarga_rifa")
    total_kk_rifa = cursor_rifa.fetchone()['total']

    cursor_rifa.execute("SELECT COUNT(*) as total FROM akta_kematian_rifa")
    akta_rifa = cursor_rifa.fetchone()['total']
    
    cursor_rifa.execute("SELECT COUNT(*) as total FROM surat_pindah_rifa")
    pindah_rifa = cursor_rifa.fetchone()['total']

    cursor_rifa.execute("SELECT COUNT(*) as total FROM izin_tinggal_rifa")
    izin_rifa = cursor_rifa.fetchone()['total']

    total_pengajuan_rifa = akta_rifa + pindah_rifa + izin_rifa

    cursor_rifa.close()
    conn_rifa.close()

    return render_template('admin/dashboard.html', 
                           nama_rifa=session['nama_lengkap_rifa'],
                           total_user=total_user_rifa,
                           total_penduduk=total_penduduk_rifa,
                           total_kk=total_kk_rifa,
                           total_pengajuan=total_pengajuan_rifa)

@app.route('/admin/penduduk')
@role_required('admin')
def data_penduduk_admin():
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)

    cursor_rifa.execute("""
        SELECT p.*, kk.*
        FROM penduduk_rifa p 
        LEFT JOIN kartu_keluarga_rifa kk ON p.no_kk_rifa = kk.no_kk_rifa
        ORDER BY p.nama_lengkap_rifa ASC
    """)
    data_penduduk_rifa = cursor_rifa.fetchall()

    cursor_rifa.close()
    conn_rifa.close()

    return render_template('admin/penduduk.html', 
                           nama_rifa=session['nama_lengkap_rifa'],
                           penduduk=data_penduduk_rifa)

@app.route('/admin/penduduk/tambah', methods=['GET'])
@role_required('admin')
def tambah_penduduk_page():
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    
    cursor_rifa.execute("SELECT no_kk_rifa, alamat_rifa, rt_rifa, rw_rifa FROM kartu_keluarga_rifa ORDER BY no_kk_rifa DESC")
    daftar_kk_rifa = cursor_rifa.fetchall()
    
    cursor_rifa.close()
    conn_rifa.close()

    return render_template('admin/penduduk/tambah.html', 
                           nama_rifa=session.get('nama_lengkap_rifa'),
                           daftar_kk_rifa=daftar_kk_rifa)

@app.route('/admin/penduduk/tambah/proses', methods=['POST'])
@role_required('admin')
def tambah_penduduk_proses():
    nik_rifa = request.form.get('nik_rifa')
    no_kk_rifa = request.form.get('no_kk_rifa')
    nama_lengkap_rifa = request.form.get('nama_lengkap_rifa')
    tempat_lahir_rifa = request.form.get('tempat_lahir_rifa')
    tanggal_lahir_rifa = request.form.get('tanggal_lahir_rifa')
    jenis_kelamin_rifa = request.form.get('jenis_kelamin_rifa')
    agama_rifa = request.form.get('agama_rifa')
    pendidikan_rifa = request.form.get('pendidikan_rifa')
    pekerjaan_rifa = request.form.get('pekerjaan_rifa')
    status_perkawinan_rifa = request.form.get('status_perkawinan_rifa')

    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor()

    try:
        query_rifa = """
            INSERT INTO penduduk_rifa (
                nik_rifa, no_kk_rifa, nama_lengkap_rifa, tempat_lahir_rifa, 
                tanggal_lahir_rifa, jenis_kelamin_rifa, agama_rifa, pendidikan_rifa, 
                pekerjaan_rifa, status_perkawinan_rifa, kewarganegaraan_rifa, status_hidup_rifa
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        values_rifa = (
            nik_rifa, no_kk_rifa, nama_lengkap_rifa, tempat_lahir_rifa, tanggal_lahir_rifa, 
            jenis_kelamin_rifa, agama_rifa, pendidikan_rifa, 
            pekerjaan_rifa, status_perkawinan_rifa, 'WNI', 'Hidup'
        )
        
        cursor_rifa.execute(query_rifa, values_rifa)
        conn_rifa.commit()
        
        flash(f'Data {nama_lengkap_rifa} berhasil ditambahkan!', 'success')
        return redirect(url_for('data_penduduk_admin'))

    except Exception as e:
        conn_rifa.rollback()
        flash(f'Terjadi kesalahan: {str(e)}', 'danger')
        return redirect(url_for('tambah_penduduk_page'))
    finally:
        cursor_rifa.close()
        conn_rifa.close()

@app.route('/admin/penduduk/edit/<nik_rifa>', methods=['GET'])
@role_required('admin')
def edit_penduduk_page(nik_rifa):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    
    cursor_rifa.execute("""
        SELECT p.*, kk.alamat_rifa, kk.rt_rifa, kk.rw_rifa 
        FROM penduduk_rifa p
        JOIN kartu_keluarga_rifa kk ON p.no_kk_rifa = kk.no_kk_rifa
        WHERE p.nik_rifa = %s
    """, (nik_rifa,))
    penduduk = cursor_rifa.fetchone()

    cursor_rifa.execute("SELECT no_kk_rifa, alamat_rifa, rt_rifa, rw_rifa FROM kartu_keluarga_rifa ORDER BY no_kk_rifa DESC")
    daftar_kk_rifa = cursor_rifa.fetchall()
    
    cursor_rifa.close()
    conn_rifa.close()

    if not penduduk:
        flash('Data penduduk tidak ditemukan!', 'danger')
        return redirect(url_for('data_penduduk_admin'))

    return render_template('admin/penduduk/edit.html', 
                           nama_rifa=session.get('nama_lengkap_rifa'),
                           penduduk=penduduk,
                           daftar_kk_rifa=daftar_kk_rifa)

@app.route('/admin/penduduk/edit/proses', methods=['POST'])
@role_required('admin')
def edit_penduduk_proses():
    nik_rifa = request.form.get('nik_rifa') 
    
    no_kk_rifa = request.form.get('no_kk_rifa')
    nama_lengkap_rifa = request.form.get('nama_lengkap_rifa')
    tempat_lahir_rifa = request.form.get('tempat_lahir_rifa')
    tanggal_lahir_rifa = request.form.get('tanggal_lahir_rifa')
    jenis_kelamin_rifa = request.form.get('jk_rifa')
    agama_rifa = request.form.get('agama_rifa')
    pendidikan_rifa = request.form.get('pendidikan_rifa')
    pekerjaan_rifa = request.form.get('pekerjaan_rifa')
    status_perkawinan_rifa = request.form.get('status_kawin_rifa')

    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor()

    try:
        query_rifa = """
            UPDATE penduduk_rifa SET 
                no_kk_rifa = %s, 
                nama_lengkap_rifa = %s, 
                tempat_lahir_rifa = %s, 
                tanggal_lahir_rifa = %s, 
                jenis_kelamin_rifa = %s, 
                agama_rifa = %s, 
                pendidikan_rifa = %s, 
                pekerjaan_rifa = %s, 
                status_perkawinan_rifa = %s
            WHERE nik_rifa = %s
        """
        values_rifa = (
            no_kk_rifa, nama_lengkap_rifa, tempat_lahir_rifa, tanggal_lahir_rifa, 
            jenis_kelamin_rifa, agama_rifa, pendidikan_rifa, 
            pekerjaan_rifa, status_perkawinan_rifa, nik_rifa
        )
        
        cursor_rifa.execute(query_rifa, values_rifa)
        conn_rifa.commit()
        
        flash(f'Data {nama_lengkap_rifa} berhasil diperbarui!', 'success')
    except Exception as e:
        conn_rifa.rollback()
        flash(f'Terjadi kesalahan saat mengupdate: {str(e)}', 'danger')
    finally:
        cursor_rifa.close()
        conn_rifa.close()

    return redirect(url_for('data_penduduk_admin'))

@app.route('/admin/penduduk/hapus/<nik_rifa>', methods=['POST'])
@role_required('admin')
def hapus_penduduk(nik_rifa):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor()

    try:
        cursor_rifa.execute("DELETE FROM penduduk_rifa WHERE nik_rifa = %s", (nik_rifa,))
        conn_rifa.commit()
        flash('Data penduduk berhasil dihapus dari sistem!', 'success')
    except Exception as e:
        conn_rifa.rollback()
        flash(f'Data tidak dapat dihapus: {str(e)}', 'danger')
    finally:
        cursor_rifa.close()
        conn_rifa.close()

    return redirect(url_for('data_penduduk_admin'))

@app.route('/admin/kartu-keluarga')
@role_required('admin')
def data_kartu_keluarga_admin():
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)

    cursor_rifa.execute("""
        SELECT kk.*, kel.nama_kelurahan_rifa 
        FROM kartu_keluarga_rifa kk
        LEFT JOIN kelurahan_rifa kel ON kk.id_kelurahan_rifa = kel.id_kelurahan_rifa
    ORDER BY kk.no_kk_rifa ASC
    """)
    data_kartu_keluarga_rifa = cursor_rifa.fetchall()

    cursor_rifa.close()
    conn_rifa.close()

    return render_template('admin/kartu-keluarga.html', 
                           nama_rifa=session['nama_lengkap_rifa'],
                           kartu_keluarga=data_kartu_keluarga_rifa)

@app.route('/admin/kartu-keluarga/tambah', methods=['GET'])
@role_required('admin')
def tambah_kartu_keluarga_page():
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)

    cursor_rifa.execute("SELECT * FROM kelurahan_rifa")
    daftar_kelurahan = cursor_rifa.fetchall()
    cursor_rifa.close()
    conn_rifa.close()

    return render_template('admin/kartu-keluarga/tambah.html', daftar_kelurahan=daftar_kelurahan)

@app.route('/admin/kartu-keluarga/tambah/proses', methods=['POST'])
@role_required('admin')
def tambah_kartu_keluarga_proses():
    no_kk_rifa = request.form.get('no_kk_rifa')
    id_kelurahan_rifa = request.form.get('id_kelurahan_rifa')
    alamat_rifa = request.form.get('alamat_rifa')
    rt_rifa = request.form.get('rt_rifa')
    rw_rifa = request.form.get('rw_rifa')
    tahun_terbit_rifa = request.form.get('tahun_terbit_rifa')

    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor()
    try:
        query = "INSERT INTO kartu_keluarga_rifa (no_kk_rifa, id_kelurahan_rifa, alamat_rifa, rt_rifa, rw_rifa, tahun_terbit_rifa) VALUES (%s, %s, %s, %s, %s, %s)"
        cursor_rifa.execute(query, (no_kk_rifa, id_kelurahan_rifa, alamat_rifa, rt_rifa, rw_rifa, tahun_terbit_rifa))
        conn_rifa.commit()
        flash('Data Kartu Keluarga berhasil ditambahkan!', 'success')
    except Exception as e:
        conn_rifa.rollback()
        flash(f'Gagal menambah data: {str(e)}', 'danger')
    finally:
        cursor_rifa.close()
        conn_rifa.close()
    return redirect(url_for('data_kartu_keluarga_admin'))

@app.route('/admin/kartu-keluarga/edit/<no_kk_rifa>', methods=['GET'])
@role_required('admin')
def edit_kartu_keluarga_page(no_kk_rifa):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)

    cursor_rifa.execute("SELECT * FROM kartu_keluarga_rifa WHERE no_kk_rifa = %s", (no_kk_rifa,))
    kk = cursor_rifa.fetchone()

    cursor_rifa.execute("SELECT * FROM kelurahan_rifa")
    daftar_kelurahan = cursor_rifa.fetchall()
    cursor_rifa.close()
    conn_rifa.close()

    return render_template('admin/kartu-keluarga/edit.html', kk=kk, daftar_kelurahan=daftar_kelurahan)

@app.route('/admin/kartu-keluarga/edit/proses', methods=['POST'])
@role_required('admin')
def edit_kartu_keluarga_proses():
    no_kk_rifa = request.form.get('no_kk_rifa')
    id_kelurahan_rifa = request.form.get('id_kelurahan_rifa')
    alamat_rifa = request.form.get('alamat_rifa')
    rt_rifa = request.form.get('rt_rifa')
    rw_rifa = request.form.get('rw_rifa')

    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor()

    try:
        query = "UPDATE kartu_keluarga_rifa SET id_kelurahan_rifa=%s, alamat_rifa=%s, rt_rifa=%s, rw_rifa=%s WHERE no_kk_rifa=%s"
        cursor_rifa.execute(query, (id_kelurahan_rifa, alamat_rifa, rt_rifa, rw_rifa, no_kk_rifa))
        conn_rifa.commit()
        flash('Data Kartu Keluarga berhasil diperbarui!', 'success')

    except Exception as e:
        conn_rifa.rollback()
        flash(f'Gagal memperbarui data: {str(e)}', 'danger')

    finally:
        cursor_rifa.close()
        conn_rifa.close()

    return redirect(url_for('data_kartu_keluarga_admin'))

@app.route('/admin/kartu-keluarga/hapus/<no_kk_rifa>')
@role_required('admin')
def hapus_kartu_keluarga(no_kk_rifa):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor()

    try:
        cursor_rifa.execute("DELETE FROM kartu_keluarga_rifa WHERE no_kk_rifa = %s", (no_kk_rifa,))
        conn_rifa.commit()
        flash('Data Kartu Keluarga berhasil dihapus!', 'success')

    except Exception as e:
        conn_rifa.rollback()
        flash('Gagal menghapus! Pastikan tidak ada anggota keluarga (penduduk) di dalam KK ini.', 'danger')

    finally:
        cursor_rifa.close()
        conn_rifa.close()

    return redirect(url_for('data_kartu_keluarga_admin'))

@app.route('/admin/pengguna')
@role_required('admin')
def data_pengguna_admin():
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)

    cursor_rifa.execute("""
        SELECT *
        FROM user_rifa
    ORDER BY id_user_rifa ASC
    """)
    data_pengguna_rifa = cursor_rifa.fetchall()

    cursor_rifa.close()
    conn_rifa.close()

    return render_template('admin/pengguna.html', 
                           nama_rifa=session['nama_lengkap_rifa'],
                           pengguna=data_pengguna_rifa)

# Belum CUD Pengguna

# Petugas

@app.route('/petugas/dashboard')
@role_required('petugas')
def dashboard_petugas():
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)

    try:
        query_rifa = """
            SELECT 'Akta Kematian' as jenis_layanan FROM akta_kematian_rifa
            UNION ALL
            SELECT 'Surat Pindah' as jenis_layanan FROM surat_pindah_rifa
            UNION ALL
            SELECT 'Izin Tinggal' as jenis_layanan FROM izin_tinggal_rifa
        """
        cursor_rifa.execute(query_rifa)
        semua_pengajuan = cursor_rifa.fetchall()
        
        total_pengajuan = len(semua_pengajuan)
        total_akta = sum(1 for item in semua_pengajuan if item['jenis_layanan'] == 'Akta Kematian')
        total_pindah = sum(1 for item in semua_pengajuan if item['jenis_layanan'] == 'Surat Pindah')
        total_izin = sum(1 for item in semua_pengajuan if item['jenis_layanan'] == 'Izin Tinggal')
        
        return render_template('petugas/dashboard.html', 
                               total_pengajuan=total_pengajuan,
                               total_akta=total_akta,
                               total_pindah=total_pindah,
                               total_izin=total_izin)

    except Exception as e:
        print("Error Dashboard Petugas:", str(e))
        return f"Terjadi kesalahan database: {str(e)}"
    
    finally:
        if 'cursor_rifa' in locals():
            cursor_rifa.close()
        if 'conn_rifa' in locals():
            conn_rifa.close()


@app.route('/petugas/verifikasi')
@role_required('petugas')
def verifikasi_petugas():
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)

    try:
        query_rifa = """
            SELECT 
                a.id_akta_kematian_rifa as id_p, 
                'Akta Kematian' as jenis_layanan, 
                p.nama_lengkap_rifa as nama_pemohon, 
                a.tanggal_pengajuan_rifa, 
                a.status_pengajuan_rifa
            FROM akta_kematian_rifa a
            JOIN penduduk_rifa p ON a.nik_pemohon_rifa = p.nik_rifa
            
            UNION ALL
            
            SELECT 
                s.id_surat_pindah_rifa as id_p, 
                'Surat Pindah' as jenis_layanan, 
                p.nama_lengkap_rifa as nama_pemohon, 
                s.tanggal_pengajuan_rifa, 
                s.status_pengajuan_rifa
            FROM surat_pindah_rifa s
            JOIN penduduk_rifa p ON s.nik_rifa = p.nik_rifa
            
            UNION ALL
            
            SELECT 
                i.id_izin_tinggal_rifa as id_p, 
                'Izin Tinggal' as jenis_layanan, 
                p.nama_lengkap_rifa as nama_pemohon, 
                i.tanggal_pengajuan_rifa, 
                i.status_pengajuan_rifa
            FROM izin_tinggal_rifa i
            JOIN penduduk_rifa p ON i.nik_pemohon_rifa = p.nik_rifa
            
            ORDER BY tanggal_pengajuan_rifa ASC
        """
        
        cursor_rifa.execute(query_rifa)
        data_pengajuan_rifa = cursor_rifa.fetchall()
        
        return render_template('petugas/verifikasi.html', data_pengajuan=data_pengajuan_rifa)

    except Exception as e:
        print("Error Verifikasi Petugas:", str(e))
        return f"Terjadi kesalahan database: {str(e)}"
    finally:
        if 'cursor_rifa' in locals(): cursor_rifa.close()
        if 'conn_rifa' in locals(): conn_rifa.close()

@app.route('/petugas/verifikasi/akta-kematian/<int:id_p>')
@role_required('petugas')
def detail_verifikasi_akta(id_p):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    
    try:
        query = """
            SELECT a.*, p.nama_lengkap_rifa AS nama_jenazah,
                   s.nik_saksi_1_rifa, s.nama_saksi_1_rifa, s.file_ktp_saksi_1_rifa, 
                   s.nik_saksi_2_rifa, s.nama_saksi_2_rifa, s.file_ktp_saksi_2_rifa 
            FROM akta_kematian_rifa a
            JOIN penduduk_rifa p ON a.nik_jenazah_rifa = p.nik_rifa
            LEFT JOIN saksi_akta_kematian_rifa s ON a.id_akta_kematian_rifa = s.id_akta_kematian_rifa
            WHERE a.id_akta_kematian_rifa = %s
        """
        cursor_rifa.execute(query, (id_p,))
        data = cursor_rifa.fetchone()
        return render_template('petugas/detail_verifikasi_akta.html', data=data)
    finally:
        cursor_rifa.close()
        conn_rifa.close()

@app.route('/petugas/verifikasi/akta-kematian/proses/<int:id_p>/<string:aksi>')
@role_required('petugas')
def proses_verifikasi_akta(id_p, aksi):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    id_petugas = session['id_user_rifa']
    
    try:
        if aksi == 'tolak':
            cursor_rifa.execute("UPDATE akta_kematian_rifa SET status_pengajuan_rifa = 'ditolak', id_petugas_user_rifa = %s WHERE id_akta_kematian_rifa = %s", (id_petugas, id_p))
            flash('Pengajuan telah ditolak.', 'warning')
            
        elif aksi == 'setujui':
            cursor_rifa.execute("SELECT nik_jenazah_rifa FROM akta_kematian_rifa WHERE id_akta_kematian_rifa = %s", (id_p,))
            nik_jenazah = cursor_rifa.fetchone()['nik_jenazah_rifa']
            
            cursor_rifa.execute("UPDATE akta_kematian_rifa SET status_pengajuan_rifa = 'disetujui', id_petugas_user_rifa = %s WHERE id_akta_kematian_rifa = %s", (id_petugas, id_p))
            
            cursor_rifa.execute("UPDATE penduduk_rifa SET status_hidup_rifa = 'Meninggal' WHERE nik_rifa = %s", (nik_jenazah,))
            
            cursor_rifa.execute("UPDATE user_rifa SET status_aktif_rifa = 0 WHERE nik_penduduk_rifa = %s", (nik_jenazah,))
            
            flash('Pengajuan disetujui, status penduduk dan akun telah diperbarui.', 'success')
            
        conn_rifa.commit()
    except Exception as e:
        conn_rifa.rollback()
        flash(f'Terjadi kesalahan: {str(e)}', 'danger')
    finally:
        cursor_rifa.close()
        conn_rifa.close()
        
    return redirect(url_for('verifikasi_petugas'))

@app.route('/cetak-akta-kematian/<int:id_p>')
@role_required_either(['masyarakat', 'petugas'])
def cetak_akta_kematian(id_p):
    role = session.get('role_rifa')
    dashboard_endpoint = 'dashboard_petugas' if role == 'petugas' else 'dashboard_masyarakat'

    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)

    try:
        query_akta = """
            SELECT a.*, 
                   p.nama_lengkap_rifa AS nama_jenazah,
                   p.tempat_lahir_rifa, p.tanggal_lahir_rifa, 
                   p.jenis_kelamin_rifa,
                   u2.nama_lengkap_rifa AS nama_petugas
            FROM akta_kematian_rifa a
            JOIN penduduk_rifa p ON a.nik_jenazah_rifa = p.nik_rifa
            LEFT JOIN user_rifa ur ON a.id_petugas_user_rifa = ur.id_user_rifa
            LEFT JOIN penduduk_rifa u2 ON ur.nik_penduduk_rifa = u2.nik_rifa
            WHERE a.id_akta_kematian_rifa = %s
        """
        cursor_rifa.execute(query_akta, (id_p,))
        data = cursor_rifa.fetchone()

        if not data or data['status_pengajuan_rifa'] != 'disetujui':
            flash('Data tidak ditemukan atau belum disetujui.', 'warning')
            return redirect(url_for(dashboard_endpoint))

    except Exception as e:
        print(f"ERROR CETAK KUTIPAN AKTA: {str(e)}")
        flash('Terjadi kesalahan sistem.', 'danger')
        return redirect(url_for(dashboard_endpoint))
    finally:
        cursor_rifa.close()
        conn_rifa.close()

    BULAN_ID = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
                'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

    tgl_cetak = f"{datetime.today().day} {BULAN_ID[datetime.today().month]} {datetime.today().year}"

    def terbilang_tanggal(tgl):
        if not tgl:
            return '-'
        return f"{tgl.day} {BULAN_ID[tgl.month]} {tgl.year}"

    garuda_path = os.path.join(app.root_path, 'static', 'img', 'garuda.png')

    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_margins(left=25, top=20, right=20)
    pdf.add_page()

    page_w = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_y(20)
    pdf.set_font("helvetica", "", 8)
    pdf.cell(page_w / 2, 4, "Nomor Induk Kependudukan", new_x="RIGHT", new_y="LAST")

    pdf.set_font("helvetica", "B", 9)
    no_am = "No. AM. 791." + str(data['id_akta_kematian_rifa']).zfill(7)
    pdf.cell(page_w / 2, 4, no_am, align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "I", 7)
    pdf.cell(page_w / 2, 3, "Personnel Registration Number", new_x="RIGHT", new_y="LAST")
    pdf.cell(page_w / 2, 3, "", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "B", 10)
    pdf.cell(page_w / 2, 5, str(data['nik_jenazah_rifa']), new_x="LMARGIN", new_y="NEXT")

    logo_w = 25
    logo_x = (pdf.w - logo_w) / 2
    logo_y = pdf.get_y() + 3

    try:
        pdf.image(garuda_path, x=logo_x, y=logo_y, w=logo_w)
    except:
        pass

    pdf.set_y(logo_y + logo_w + 3)

    pdf.set_font("helvetica", "B", 13)
    pdf.cell(0, 7, "PENCATATAN SIPIL", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 5, "REGISTRY OFFICE", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)

    pdf.set_font("helvetica", "", 10)
    pdf.cell(35, 5, "WARGA NEGARA", new_x="RIGHT", new_y="LAST")
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(page_w - 35, 5, "WARGA NEGARA INDONESIA", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "I", 8)
    pdf.cell(0, 4, "NATIONALITY", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)

    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 7, "KUTIPAN AKTA KEMATIAN", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "I", 9)
    pdf.cell(0, 5, "EXCERPT OF DEATH CERTIFICATE", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)

    no_akta = f"{data['id_akta_kematian_rifa']}/KU/{data['tanggal_meninggal_rifa'].year}"

    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, "Berdasarkan Akta Kematian Nomor", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "I", 8)
    pdf.cell(0, 4, "By virtue of Death Certificate Number", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "B", 10)
    pdf.cell(page_w, 6, no_akta, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)

    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, "pada tanggal", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "I", 8)
    pdf.cell(0, 4, "on date", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "B", 10)
    pdf.cell(page_w, 6, terbilang_tanggal(data['tanggal_meninggal_rifa']), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)

    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, "tahun", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "I", 8)
    pdf.cell(0, 4, "year", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "B", 10)
    pdf.cell(page_w, 6, str(data['tanggal_meninggal_rifa'].year), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)

    title_prefix = "Tn." if data['jenis_kelamin_rifa'] == 'L' else "Ny/Nn."

    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, f"telah meninggal dunia seorang bernama {title_prefix}", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "I", 8)
    pdf.cell(0, 4, "a deceased person named", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "B", 11)
    pdf.cell(page_w, 7, data['nama_jenazah'].upper(), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)

    pdf.set_font("helvetica", "", 9)
    pdf.cell(page_w * 0.45, 5, "lahir di", new_x="RIGHT", new_y="LAST")
    pdf.cell(page_w * 0.55, 5, "pada tanggal", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "I", 8)
    pdf.cell(page_w * 0.45, 4, "born in", new_x="RIGHT", new_y="LAST")
    pdf.cell(page_w * 0.55, 4, "on date", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "B", 10)
    tgl_lahir_str = f"{data['tanggal_lahir_rifa'].day} {BULAN_ID[data['tanggal_lahir_rifa'].month]}"

    pdf.cell(page_w * 0.45, 6, data['tempat_lahir_rifa'].upper(), new_x="RIGHT", new_y="LAST")
    pdf.cell(page_w * 0.55, 6, tgl_lahir_str, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, "tahun", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "I", 8)
    pdf.cell(0, 4, "year", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 6, str(data['tanggal_lahir_rifa'].year), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)

    right_col_x = pdf.l_margin + page_w * 0.5

    pdf.set_x(right_col_x)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(page_w * 0.5, 5, "Kutipan ini dikeluarkan", new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(right_col_x)
    pdf.set_font("helvetica", "", 9)
    pdf.cell(page_w * 0.5, 5, "pada tanggal", new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(right_col_x)
    pdf.set_font("helvetica", "B", 10)
    pdf.cell(page_w * 0.5, 6, tgl_cetak, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(20)

    pdf.set_x(right_col_x)
    pdf.set_font("helvetica", "BU", 10)
    pdf.cell(page_w * 0.5, 5, "KEPALA DINAS PENCATATAN SIPIL", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf_bytes = pdf.output()
    buffer = io.BytesIO(pdf_bytes)

    return send_file(buffer, as_attachment=False, mimetype='application/pdf')

@app.route('/petugas/verifikasi/surat-pindah/<int:id_p>')
@role_required('petugas')
def detail_verifikasi_pindah(id_p):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    
    try:
        query_pindah = """
            SELECT s.*, p.nama_lengkap_rifa AS nama_pemohon, k.nama_kelurahan_rifa
            FROM surat_pindah_rifa s
            JOIN penduduk_rifa p ON s.nik_rifa = p.nik_rifa
            LEFT JOIN kelurahan_rifa k ON s.id_kelurahan_rifa = k.id_kelurahan_rifa
            WHERE s.id_surat_pindah_rifa = %s
        """
        cursor_rifa.execute(query_pindah, (id_p,))
        data = cursor_rifa.fetchone()

        query_anggota = "SELECT * FROM anggota_pindah_rifa WHERE id_surat_pindah_rifa = %s"
        cursor_rifa.execute(query_anggota, (id_p,))
        anggota = cursor_rifa.fetchall()

        return render_template('petugas/detail_verifikasi_pindah.html', data=data, anggota=anggota)
    finally:
        cursor_rifa.close()
        conn_rifa.close()

@app.route('/petugas/verifikasi/surat-pindah/proses/<int:id_p>/<string:aksi>')
@role_required('petugas')
def proses_verifikasi_pindah(id_p, aksi):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    id_petugas = session['id_user_rifa']
    
    try:
        if aksi == 'tolak':
            cursor_rifa.execute("UPDATE surat_pindah_rifa SET status_pengajuan_rifa = 'ditolak', id_petugas_user_rifa = %s WHERE id_surat_pindah_rifa = %s", (id_petugas, id_p))
            flash('Pengajuan pindah ditolak.', 'warning')
            
        elif aksi == 'setujui':
            cursor_rifa.execute("SELECT nik_rifa, id_kelurahan_rifa FROM surat_pindah_rifa WHERE id_surat_pindah_rifa = %s", (id_p,))
            data_pindah = cursor_rifa.fetchone()
            nik_pemohon = data_pindah['nik_rifa']
            kelurahan_tujuan = data_pindah['id_kelurahan_rifa']
            
            cursor_rifa.execute("SELECT nik_rifa FROM anggota_pindah_rifa WHERE id_surat_pindah_rifa = %s", (id_p,))
            daftar_anggota = cursor_rifa.fetchall()
            
            semua_nik = [nik_pemohon]
            for anggota in daftar_anggota:
                semua_nik.append(anggota['nik_rifa'])
            
            format_strings = ','.join(['%s'] * len(semua_nik))
            
            cursor_rifa.execute("UPDATE surat_pindah_rifa SET status_pengajuan_rifa = 'disetujui', id_petugas_user_rifa = %s WHERE id_surat_pindah_rifa = %s", (id_petugas, id_p))
            
            if kelurahan_tujuan is None:
                cursor_rifa.execute(f"UPDATE user_rifa SET status_aktif_rifa = 0 WHERE nik_penduduk_rifa IN ({format_strings})", tuple(semua_nik))
                flash('Surat pindah keluar wilayah disetujui. Akun penduduk terkait telah dinonaktifkan.', 'success')
            else:
                flash('Surat pindah antar kelurahan disetujui. Silakan arahkan warga untuk memperbarui/membuat KK baru.', 'success')
            
        conn_rifa.commit()
    except Exception as e:
        conn_rifa.rollback()
        flash(f'Gagal memproses: {str(e)}', 'danger')
    finally:
        cursor_rifa.close()
        conn_rifa.close()
        
    return redirect(url_for('verifikasi_petugas'))

@app.route('/cetak-surat-pindah/<int:id_p>')
@role_required_either(['masyarakat', 'petugas'])
def cetak_surat_pindah(id_p):
    role = session.get('role_rifa')
    dashboard_endpoint = 'dashboard_petugas' if role == 'petugas' else 'dashboard_masyarakat'

    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    
    try:
        query_pindah = """
            SELECT s.*, p.nama_lengkap_rifa AS nama_pemohon, p.no_kk_rifa,
                   k.nama_kelurahan_rifa AS kelurahan_asal,
                   u2.nama_lengkap_rifa AS nama_petugas
            FROM surat_pindah_rifa s
            JOIN penduduk_rifa p ON s.nik_rifa = p.nik_rifa
            LEFT JOIN kelurahan_rifa k ON s.id_kelurahan_rifa = k.id_kelurahan_rifa
            LEFT JOIN user_rifa ur ON s.id_petugas_user_rifa = ur.id_user_rifa
            LEFT JOIN penduduk_rifa u2 ON ur.nik_penduduk_rifa = u2.nik_rifa
            WHERE s.id_surat_pindah_rifa = %s
        """
        cursor_rifa.execute(query_pindah, (id_p,))
        data = cursor_rifa.fetchone()

        if not data or data['status_pengajuan_rifa'] != 'disetujui':
            flash('Data tidak ditemukan atau belum disetujui.', 'warning')
            return redirect(url_for(dashboard_endpoint))

        query_anggota = """
            SELECT a.nik_rifa, a.status_keluarga_rifa, p.nama_lengkap_rifa 
            FROM anggota_pindah_rifa a
            JOIN penduduk_rifa p ON a.nik_rifa = p.nik_rifa
            WHERE a.id_surat_pindah_rifa = %s
        """
        cursor_rifa.execute(query_anggota, (id_p,))
        anggota = cursor_rifa.fetchall()

    except Exception as e:
        print(f"ERROR CETAK SURAT PINDAH: {str(e)}")
        flash('Terjadi kesalahan sistem.', 'danger')
        return redirect(url_for(dashboard_endpoint))
    finally:
        cursor_rifa.close()
        conn_rifa.close()

    BULAN_ID = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
    tgl_cetak = f"{datetime.today().day} {BULAN_ID[datetime.today().month]} {datetime.today().year}"
    
    logo_path = os.path.join(app.root_path, 'static', 'img', 'logo_cimahi.png')

    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_margins(left=20, top=15, right=20)
    pdf.add_page()

    try:
        pdf.image(logo_path, x=22, y=17, w=18)
    except:
        pass

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 6, "PEMERINTAH KOTA CIMAHI", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 7, "KECAMATAN CIMAHI UTARA", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 8, f"KELURAHAN {(data.get('kelurahan_asal') or 'CIBABAT').upper()}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "I", 8)
    pdf.cell(0, 5, "Jl. Jati Serut No.12, Cibabat, Kec. Cimahi Utara, Kota Cimahi, Jawa Barat 40513", align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_line_width(0.8)
    pdf.line(20, 47, 190, 47)
    pdf.ln(10)

    pdf.set_font("helvetica", "BU", 13)
    pdf.cell(0, 7, "SURAT KETERANGAN PINDAH", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 5, f"Nomor : 475 / {data['id_surat_pindah_rifa']} / {datetime.today().year}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 7, "DATA DAERAH ASAL", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)

    def add_row(label, value, indent=5):
        pdf.set_x(20 + indent)
        pdf.cell(45, 6, label)
        pdf.cell(5, 6, ":")
        pdf.set_font("helvetica", "B", 10)
        pdf.multi_cell(0, 6, str(value), align="L")
        pdf.set_font("helvetica", "", 10)

    add_row("1. Nomor Kartu Keluarga", data.get('no_kk_rifa', '-'))
    add_row("2. Nama Kepala Keluarga", data.get('nama_pemohon', '-'))
    add_row("3. NIK Pemohon", data.get('nik_rifa', '-'))
    add_row("4. Alamat Asal", data.get('alamat_asal_rifa', '-'))
    pdf.ln(3)

    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 7, "DATA DAERAH TUJUAN PINDAH", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    
    add_row("1. Alamat Tujuan", data.get('alamat_tujuan_rifa', '-'))
    add_row("2. Alasan Pindah", data.get('alasan_pindah_rifa', '-'))
    pdf.ln(5)

    pdf.set_font("helvetica", "B", 10)
    pdf.cell(0, 7, "DAFTAR KELUARGA YANG PINDAH", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(10, 8, "No", border=1, align="C", fill=True)
    pdf.cell(45, 8, "NIK", border=1, align="C", fill=True)
    pdf.cell(75, 8, "Nama Lengkap", border=1, align="C", fill=True)
    pdf.cell(40, 8, "Hubungan", border=1, align="C", fill=True, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("helvetica", "", 9)
    if anggota:
        for idx, person in enumerate(anggota, 1):
            pdf.cell(10, 7, str(idx), border=1, align="C")
            pdf.cell(45, 7, person['nik_rifa'], border=1, align="C")
            pdf.cell(75, 7, person['nama_lengkap_rifa'].upper(), border=1)
            pdf.cell(40, 7, person['status_keluarga_rifa'], border=1, new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(170, 7, "Hanya pemohon sendiri yang pindah", border=1, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(10)
    pdf.set_font("helvetica", "", 10)
    pdf.multi_cell(0, 5, "Demikian Surat Keterangan Pindah ini dibuat dengan sebenarnya untuk digunakan sebagaimana mestinya.", align="J")

    pdf.ln(10)
    pdf.set_x(130)
    pdf.cell(60, 6, f"Cimahi, {tgl_cetak}", align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(130)
    pdf.cell(60, 6, "Kepala Kelurahan,", align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(20)
    pdf.set_x(130)
    pdf.set_font("helvetica", "B", 10)
    nama_lurah = "Kepala Kelurahan".upper()
    pdf.cell(60, 6, nama_lurah, align="L")

    pdf_bytes = pdf.output()
    buffer = io.BytesIO(pdf_bytes)
    
    return send_file(
        buffer, 
        as_attachment=False, 
        mimetype='application/pdf'
    )

@app.route('/petugas/verifikasi/izin-tinggal/proses/<int:id_p>/<string:aksi>')
@role_required('petugas')
def proses_verifikasi_izin(id_p, aksi):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor()
    id_petugas = session['id_user_rifa']
    
    try:
        if aksi == 'tolak':
            cursor_rifa.execute("UPDATE izin_tinggal_rifa SET status_pengajuan_rifa = 'ditolak', id_petugas_rifa = %s WHERE id_izin_tinggal_rifa = %s", (id_petugas, id_p))
            flash('Pengajuan Izin Tinggal telah ditolak.', 'warning')
        elif aksi == 'setujui':
            cursor_rifa.execute("UPDATE izin_tinggal_rifa SET status_pengajuan_rifa = 'disetujui', id_petugas_rifa = %s WHERE id_izin_tinggal_rifa = %s", (id_petugas, id_p))
            flash('Pengajuan Izin Tinggal berhasil disetujui.', 'success')
            
        conn_rifa.commit()
    except Exception as e:
        conn_rifa.rollback()
        flash(f'Gagal memproses Izin Tinggal: {str(e)}', 'danger')
    finally:
        cursor_rifa.close()
        conn_rifa.close()
        
    return redirect(url_for('verifikasi_petugas'))

@app.route('/petugas/verifikasi/izin-tinggal/<int:id_p>')
@role_required('petugas')
def detail_verifikasi_izin(id_p):
    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    try:
        query_izin = """
            SELECT i.*, p.nama_lengkap_rifa AS nama_pemohon, k.nama_kelurahan_rifa 
            FROM izin_tinggal_rifa i
            JOIN penduduk_rifa p ON i.nik_pemohon_rifa = p.nik_rifa
            JOIN kelurahan_rifa k ON i.id_kelurahan_rifa = k.id_kelurahan_rifa
            WHERE i.id_izin_tinggal_rifa = %s
        """
        cursor_rifa.execute(query_izin, (id_p,))
        data = cursor_rifa.fetchone()
        return render_template('petugas/detail_verifikasi_izin.html', data=data)
    finally:
        cursor_rifa.close()
        conn_rifa.close()

@app.route('/cetak-izin/<int:id_p>')
@role_required_either(['masyarakat', 'petugas'])
def cetak_izin_tinggal(id_p):
    role = session.get('role_rifa')
    dashboard_endpoint = 'dashboard_petugas' if role == 'petugas' else 'dashboard_masyarakat'

    conn_rifa = get_connection()
    cursor_rifa = conn_rifa.cursor(dictionary=True)
    
    try:
        query_izin = """
            SELECT i.*, p.nama_lengkap_rifa AS nama_pemohon,
                   p.tempat_lahir_rifa, p.tanggal_lahir_rifa, p.agama_rifa,
                   k.nama_kelurahan_rifa,
                   u2.nama_lengkap_rifa AS nama_petugas
            FROM izin_tinggal_rifa i
            JOIN penduduk_rifa p ON i.nik_pemohon_rifa = p.nik_rifa
            JOIN kelurahan_rifa k ON i.id_kelurahan_rifa = k.id_kelurahan_rifa
            LEFT JOIN user_rifa ur ON i.id_petugas_rifa = ur.id_user_rifa
            LEFT JOIN penduduk_rifa u2 ON ur.nik_penduduk_rifa = u2.nik_rifa
            WHERE i.id_izin_tinggal_rifa = %s
        """
        cursor_rifa.execute(query_izin, (id_p,))
        data = cursor_rifa.fetchone()

        if not data or data['status_pengajuan_rifa'] != 'disetujui':
            flash('Data tidak ditemukan atau belum disetujui.', 'warning')
            return redirect(url_for(dashboard_endpoint))

        if session.get('role_rifa') == 'masyarakat':
            if data['id_user_rifa'] != session.get('id_user_rifa'):
                flash('Anda tidak memiliki akses.', 'danger')
                return redirect(url_for(dashboard_endpoint))

    except Exception as e:
        flash('Terjadi kesalahan sistem.', 'danger')
        return redirect(url_for(dashboard_endpoint))
    finally:
        cursor_rifa.close()
        conn_rifa.close()

    BULAN_ID = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
    
    def fmt_tgl(d):
        if not d: return '-'
        return f"{d.day} {BULAN_ID[d.month]} {d.year}"

    tgl_cetak = f"{datetime.today().day} {BULAN_ID[datetime.today().month]} {datetime.today().year}"
    ttl_pemohon = f"{data['tempat_lahir_rifa']}, {data['tanggal_lahir_rifa'].strftime('%d-%m-%Y')}"
    kelurahan = (data.get('nama_kelurahan_rifa') or 'Cimahi Utara').upper()
    tgl_mulai = fmt_tgl(data.get('tanggal_mulai_rifa'))
    tgl_berakhir = fmt_tgl(data.get('tanggal_berakhir_rifa'))
    jangka_waktu = f"{tgl_mulai} s.d {tgl_berakhir}"
    
    logo_path = os.path.join(app.root_path, 'static', 'img', 'logo_cimahi.png')

    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_margins(left=25, top=20, right=20)
    pdf.add_page()
    
    try:
        pdf.image(logo_path, x=27, y=18, w=22) 
    except Exception:
        pass

    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 6, "PEMERINTAH KOTA CIMAHI", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 7, "KECAMATAN CIMAHI UTARA", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 8, f"KELURAHAN {kelurahan}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "I", 8)
    pdf.cell(0, 5, "Jl. Jati Serut No.12, Cibabat, Kec. Cimahi Utara, Kota Cimahi, Jawa Barat 40513", align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_line_width(0.8)
    pdf.line(25, 48, 190, 48)
    pdf.ln(12)

    pdf.set_font("helvetica", "B", 13)
    pdf.cell(0, 7, "SURAT KETERANGAN IZIN TINGGAL", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 5, f"Nomor : 470 / {data['id_izin_tinggal_rifa']} / {datetime.today().year}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.set_font("helvetica", "", 10)
    pdf.multi_cell(0, 6, f"Kepala Kelurahan {kelurahan.title()}, Kecamatan Cimahi Utara, Kota Cimahi, menerangkan bahwa:", align="J")
    pdf.ln(4)

    def add_row(label, value):
        pdf.set_x(35)
        pdf.set_font("helvetica", "", 10)

        pdf.cell(40, 7, label)
        pdf.cell(5, 7, ":")

        pdf.set_font("helvetica", "B", 10)
        pdf.cell(0, 7, str(value), new_x="LMARGIN", new_y="NEXT")


    def add_row_multi(label, value):
        pdf.set_x(35)
        pdf.set_font("helvetica", "", 10)

        pdf.cell(40, 6, label)
        pdf.cell(5, 6, ":")

        pdf.set_font("helvetica", "B", 10)
        pdf.multi_cell(0, 6, str(value))

    add_row("Nama Lengkap", data['nama_pemohon'])
    add_row("Tempat/Tgl Lahir", ttl_pemohon)
    add_row("Alamat Tujuan", data.get('alamat_tujuan_rifa', '-'))
    add_row("Masa Berlaku", jangka_waktu)

    keterangan = data.get('keterangan_rifa') or "Tidak ada keterangan tambahan."
    add_row_multi("Keterangan", keterangan)

    pdf.ln(5)

    pdf.set_font("helvetica", "", 10)
    pdf.multi_cell(0, 6, "Demikian surat keterangan ini dibuat untuk dipergunakan sebagaimana mestinya.", align="J")

    pdf.ln(15)
    pdf.set_x(130) 
    pdf.cell(60, 6, f"Cimahi, {tgl_cetak}", align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(130)
    pdf.cell(60, 6, "Kepala Kelurahan " + kelurahan + ",", align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(20)
    pdf.set_x(130)
    pdf.set_font("helvetica", "B", 10)
    nama_lurah = "Kepala Kelurahan".upper()
    pdf.cell(60, 6, nama_lurah, align="L")

    pdf_bytes = pdf.output()
    buffer = io.BytesIO(pdf_bytes)
    
    return send_file(
        buffer, 
        as_attachment=False, 
        mimetype='application/pdf'
    )

@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah keluar dari sistem.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)