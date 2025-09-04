import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import datetime
import os
import sys
import configparser
import webbrowser
import re
import serial
import serial.tools.list_ports
import threading
import time

try:
    import pymysql
    import pymysql.cursors
except ImportError:
    messagebox.showerror(
        "Dependência Faltando",
        "A biblioteca 'PyMySQL' é necessária.\n"
        "Por favor, instale-a executando:\npip install PyMySQL"
    )
    sys.exit(1)

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.lib import colors
except ImportError:
    messagebox.showerror(
        "Dependência Faltando",
        "A biblioteca 'reportlab' é necessária para gerar PDFs.\n"
        "Por favor, instale-a executando:\npip install reportlab"
    )
    sys.exit(1)


class BalancaReader(threading.Thread):
    def __init__(self, port, baud_rate=9600):
        super().__init__()
        self.port = port
        self.baud_rate = baud_rate
        self.serial_connection = None
        self.peso_atual = "0.00"
        self.running = True
        self.daemon = True

    def run(self):
        while self.running:
            if not self.serial_connection or not self.serial_connection.is_open:
                try:
                    self.serial_connection = serial.Serial(
                        port=self.port,
                        baudrate=self.baud_rate,
                        timeout=1
                    )
                    time.sleep(2)
                except serial.SerialException:
                    self.serial_connection = None
                    time.sleep(5)
                    continue

            try:
                if self.serial_connection.in_waiting > 0:
                    resposta = self.serial_connection.read_until(b'\r\n')
                    if resposta:
                        resposta_decodificada = resposta.decode('utf-8').strip()
                        match = re.search(r'[\d\.]+', resposta_decodificada)
                        if match:
                            self.peso_atual = f"{float(match.group()):.2f}"
            except (serial.SerialException, Exception):
                if self.serial_connection:
                    self.serial_connection.close()
                self.serial_connection = None
            time.sleep(0.1)

    def stop(self):
        self.running = False
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()

    def get_peso(self):
        return self.peso_atual

    @staticmethod
    def encontrar_porta_balanca():
        portas_disponiveis = serial.tools.list_ports.comports()
        for porta in portas_disponiveis:
            if "USB" in porta.description.upper() or "SERIAL" in porta.description.upper():
                return porta.device
        return None


class SegundaPesagemWindow(tk.Toplevel):
    def __init__(self, parent_app, pending_id, pending_data):
        super().__init__(parent_app.master)
        self.parent_app = parent_app
        self.pending_id = pending_id
        self.pending_data = pending_data
        self.is_tara_first_flow = float(self.pending_data.get('peso_bruto', 0)) < 0
        self.title("Registar 2ª Pesagem")
        self.geometry("450x500" if self.is_tara_first_flow else "450x420")
        self.resizable(False, False)
        self.transient(parent_app.master)
        self.grab_set()
        self.create_widgets()
        self.second_weight_entry.focus()
        self.update_live_weight()

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        ttk.Label(main_frame, text="Finalizar Pesagem", font=("Arial", 14, "bold")).pack(pady=(0, 10))

        info_frame = ttk.LabelFrame(main_frame, text="Dados da Entrada", padding="10")
        info_frame.pack(fill="x", pady=5)
        ttk.Label(info_frame, text=f"Placa Cavalo: {self.pending_data.get('placa', '')}").pack(anchor="w")
        if self.pending_data.get('placa_carreta'):
            ttk.Label(info_frame, text=f"Placa Carreta: {self.pending_data.get('placa_carreta', '')}").pack(anchor="w")

        if self.is_tara_first_flow:
            stored_tara = abs(float(self.pending_data.get('peso_bruto', 0)))
            ttk.Label(info_frame, text=f"Peso Tara (1ª Pesagem): {stored_tara:.2f} kg").pack(anchor="w", pady=(5, 0))
        else:
            if self.pending_data.get('tipo_carga'):
                ttk.Label(info_frame,
                          text=f"Tipo de Carga (1ª Pesagem): {self.pending_data.get('tipo_carga', '')}").pack(
                    anchor="w")
            ttk.Label(info_frame,
                      text=f"Peso Bruto (1ª Pesagem): {self.pending_data.get('peso_bruto', 0):.2f} kg").pack(anchor="w",
                                                                                                             pady=(5,
                                                                                                                   0))

        ttk.Label(info_frame, text=f"Motorista: {self.pending_data.get('motorista', '')}").pack(anchor="w")

        live_weight_frame = ttk.LabelFrame(main_frame, text="Leitura da Balança", padding="10")
        live_weight_frame.pack(fill="x", pady=10)
        self.live_weight_label = ttk.Label(live_weight_frame, text="Conectando...", font=("Arial", 18, "bold"))
        self.live_weight_label.pack(fill="x", pady=5, padx=5)

        second_weighing_frame = ttk.Frame(main_frame, padding="10")
        second_weighing_frame.pack(fill="x", pady=5)

        if self.is_tara_first_flow:
            ttk.Label(second_weighing_frame, text="Tipo de Carga:", font=("Arial", 10, "bold")).grid(row=0, column=0,
                                                                                                     padx=(0, 10),
                                                                                                     pady=5, sticky="w")
            self.tipo_carga_entry = ttk.Entry(second_weighing_frame, width=25, font=("Arial", 10))
            self.tipo_carga_entry.grid(row=0, column=1, pady=5, sticky="w")
            ttk.Label(second_weighing_frame, text="Peso Bruto (kg):", font=("Arial", 10, "bold")).grid(row=1, column=0,
                                                                                                       padx=(0, 10),
                                                                                                       pady=5,
                                                                                                       sticky="w")
            self.second_weight_entry = ttk.Entry(second_weighing_frame, width=25, font=("Arial", 10))
            self.second_weight_entry.grid(row=1, column=1, pady=5, sticky="w")
        else:
            ttk.Label(second_weighing_frame, text="Peso Tara (kg):", font=("Arial", 10, "bold")).grid(row=0, column=0,
                                                                                                      padx=(0, 10))
            self.second_weight_entry = ttk.Entry(second_weighing_frame, width=20, font=("Arial", 10))
            self.second_weight_entry.grid(row=0, column=1)

        self.finalize_button = ttk.Button(main_frame, text="Finalizar e Gerar Ticket", command=self.finalizar_pesagem,
                                          style="Success.TButton")
        self.finalize_button.pack(pady=10)

    def update_live_weight(self):
        if self.parent_app.balanca_reader and self.parent_app.balanca_reader.is_alive():
            peso = self.parent_app.balanca_reader.get_peso()
            self.live_weight_label.config(text=f"{peso} kg")
            self.after(500, self.update_live_weight)
        else:
            self.live_weight_label.config(text="Balança Desconectada")

    def finalizar_pesagem(self):
        self.finalize_button.config(state="disabled")
        second_weight_str = self.second_weight_entry.get().strip().replace(',', '.')

        try:
            if self.is_tara_first_flow:
                tipo_carga = self.tipo_carga_entry.get().strip()
                if not second_weight_str or not tipo_carga:
                    messagebox.showwarning("Campos Vazios", "Por favor, insira o Tipo de Carga e o Peso Bruto.",
                                           parent=self)
                    self.finalize_button.config(state="normal")
                    return
                peso_bruto = float(second_weight_str)
                peso_tara = abs(float(self.pending_data.get('peso_bruto', 0)))
                if peso_bruto <= 0 or peso_bruto <= peso_tara:
                    messagebox.showerror("Erro de Validação", "Peso Bruto inválido ou menor/igual à Tara.", parent=self)
                    self.finalize_button.config(state="normal")
                    return
            else:
                if not second_weight_str:
                    messagebox.showwarning("Campo Vazio", "Por favor, insira o Peso Tara.", parent=self)
                    self.finalize_button.config(state="normal")
                    return
                peso_tara = float(second_weight_str)
                peso_bruto = float(self.pending_data.get('peso_bruto', 0))
                tipo_carga = self.pending_data.get('tipo_carga')
                if peso_tara <= 0 or peso_bruto <= peso_tara:
                    messagebox.showerror("Erro de Validação", "Valores de peso inválidos.", parent=self)
                    self.finalize_button.config(state="normal")
                    return
        except ValueError:
            messagebox.showerror("Erro de Validação", "Por favor, insira um número válido para o peso.", parent=self)
            self.finalize_button.config(state="normal")
            return

        peso_liquido = peso_bruto - peso_tara
        data_hora_final = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = None
        try:
            conn = self.parent_app.get_db_connection(show_error=True)
            if conn is None:
                self.finalize_button.config(state="normal")
                return

            with conn.cursor() as cursor:
                sql_insert_ticket = """
                                    INSERT INTO tickets (data_hora, placa, placa_carreta, motorista, origem, destino,
                                                         tipo_carga, peso_tara, peso_bruto, peso_liquido)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                    """
                ticket_data = (
                    data_hora_final, self.pending_data['placa'], self.pending_data.get('placa_carreta'),
                    self.pending_data['motorista'], self.pending_data['origem'], self.pending_data['destino'],
                    tipo_carga, peso_tara, peso_bruto, peso_liquido
                )
                cursor.execute(sql_insert_ticket, ticket_data)
                ticket_id = cursor.lastrowid
                sql_delete_pending = "DELETE FROM pesagens_pendentes WHERE id = %s"
                cursor.execute(sql_delete_pending, (self.pending_id,))
            conn.commit()

            messagebox.showinfo("Sucesso", f"Ticket ID {ticket_id} finalizado com sucesso!")
            self.destroy()
            self.parent_app.load_pending_weighings()
            self.parent_app.load_history()
            if messagebox.askyesno("Gerar PDF", "Deseja gerar o PDF do ticket agora?"):
                self.parent_app.gerar_e_abrir_pdf(ticket_id)
        except pymysql.Error as err:
            messagebox.showerror("Erro de Banco de Dados", f"Não foi possível finalizar o ticket: {err}", parent=self)
            self.finalize_button.config(state="normal")
        finally:
            if conn:
                conn.close()


class BalancaApp:
    def __init__(self, master):
        self.master = master
        master.title("Gerador de Tickets de Balança v9.9 (Personalizado)")
        master.geometry("850x700")
        master.minsize(800, 600)

        self.config_file = "config.ini"
        self.app_config = {}
        self.settings_map = {
            "Nome da Empresa:": "nome", "CNPJ:": "cnpj", "Endereço Completo:": "endereco",
            "Telefone/Contato:": "contato", "Caminho do Logo (opcional):": "logopath",
            "Modelo da Balança:": "modelo_balanca",
            "MySQL Host:": "mysql_host", "MySQL Utilizador:": "mysql_user",
            "MySQL Palavra-passe:": "mysql_password", "MySQL Base de Dados:": "mysql_database"
        }
        self.load_config()

        self.style = ttk.Style(master)
        self.style.theme_use("clam")
        self.configure_styles()

        main_container = ttk.Frame(master)
        main_container.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(main_container)
        self.notebook.pack(pady=(10, 0), padx=10, fill="both", expand=True)

        status_bar_frame = ttk.Frame(main_container, padding=(10, 5))
        status_bar_frame.pack(side="bottom", fill="x")

        self.status_canvas = tk.Canvas(status_bar_frame, width=15, height=15, highlightthickness=0)
        self.status_canvas.pack(side="left", padx=(0, 5), pady=2)
        self.status_circle = self.status_canvas.create_oval(2, 2, 14, 14, fill="red", outline="")
        ttk.Label(status_bar_frame, text="Status da Conexão").pack(side="left")

        exit_button = ttk.Button(status_bar_frame, text="Sair", command=master.quit, style="Danger.TButton", width=15)
        exit_button.pack(side="right")

        self.main_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.main_frame, text="1ª Pesagem (Entrada)")
        self.pending_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.pending_frame, text="Pesagens em Andamento")
        self.history_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.history_frame, text="Histórico de Tickets")
        self.settings_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.settings_frame, text="Configurações")

        self.create_first_weighing_widgets()
        self.create_pending_widgets()
        self.create_history_widgets()
        self.create_settings_widgets()

        self.balanca_reader = None
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.master.after(100, self.initial_load)

    def configure_styles(self):
        self.style.configure("TLabel", font=("Arial", 10))
        self.style.configure("TButton", font=("Arial", 10, "bold"), padding=5)
        self.style.configure("TLabelframe.Label", font=("Arial", 11, "bold"))
        self.style.configure("Success.TButton", foreground="white", background="#4CAF50")
        self.style.map("Success.TButton", background=[('active', '#45a049')])
        self.style.configure("Warning.TButton", foreground="black", background="#FFC107")
        self.style.map("Warning.TButton", background=[('active', '#ffb300')])
        self.style.configure("Info.TButton", foreground="white", background="#2196F3")
        self.style.map("Info.TButton", background=[('active', '#1e88e5')])
        self.style.configure("Danger.TButton", foreground="white", background="#F44336")
        self.style.map("Danger.TButton", background=[('active', '#e53935')])
        self.style.configure("Treeview.Heading", font=('Arial', 10, 'bold'))

    def on_closing(self):
        if self.balanca_reader:
            self.balanca_reader.stop()
        self.master.destroy()

    def initial_load(self):
        self.load_pending_weighings()
        self.load_history()
        self.periodic_connection_check()
        self.iniciar_leitor_balanca()
        self.update_live_weight_display()

    def iniciar_leitor_balanca(self):
        porta = BalancaReader.encontrar_porta_balanca()
        if porta:
            self.balanca_reader = BalancaReader(porta)
            self.balanca_reader.start()
        else:
            messagebox.showwarning("Balança", "Não foi possível encontrar a balança.\nVerifique a conexão.")

    def update_status_indicator(self, is_connected):
        color = "green" if is_connected else "red"
        self.status_canvas.itemconfig(self.status_circle, fill=color)

    def get_db_connection(self, show_error=False):
        try:
            conn = pymysql.connect(
                host=self.app_config.get('mysql_host'),
                user=self.app_config.get('mysql_user'),
                password=self.app_config.get('mysql_password'),
                database=self.app_config.get('mysql_database'),
                connect_timeout=5,
                cursorclass=pymysql.cursors.DictCursor
            )
            self.update_status_indicator(True)
            return conn
        except pymysql.Error as err:
            self.update_status_indicator(False)
            if show_error:
                messagebox.showerror("Erro de Conexão", f"Não foi possível conectar ao MySQL: {err}")
        return None

    def periodic_connection_check(self):
        conn = self.get_db_connection(show_error=False)
        if conn:
            conn.close()
        self.master.after(60000, self.periodic_connection_check)

    def format_license_plate(self, plate_str):
        if not plate_str: return ""
        cleaned_plate = re.sub(r'[^A-Z0-9]', '', plate_str.upper())
        if len(cleaned_plate) == 7:
            return f"{cleaned_plate[:3]}-{cleaned_plate[3:]}"
        return cleaned_plate

    def _format_plate_entry(self, event):
        widget = event.widget
        current_text = widget.get()
        formatted_text = self.format_license_plate(current_text)
        if current_text != formatted_text:
            widget.delete(0, tk.END)
            widget.insert(0, formatted_text)

    def load_config(self):
        config = configparser.ConfigParser()
        if os.path.exists(self.config_file):
            config.read(self.config_file, encoding='utf-8')
            if 'Configuracoes' in config:
                self.app_config = dict(config['Configuracoes'])

    def save_config(self):
        config = configparser.ConfigParser()
        config['Configuracoes'] = {key: self.settings_entries[label_text].get() for label_text, key in
                                   self.settings_map.items()}
        try:
            with open(self.config_file, 'w', encoding='utf-8') as configfile:
                config.write(configfile)
            self.load_config()
            messagebox.showinfo("Sucesso", "Configurações salvas com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar as configurações: {e}")

    def registrar_primeira_pesagem(self):
        weighing_type = self.weighing_type.get()

        placa_cavalo = self.entries["Placa Cavalo:"].get()
        placa_carreta = self.entries["Placa Carreta:"].get()
        motorista = self.entries["Motorista:"].get().strip()
        origem = self.entries["Origem:"].get().strip()
        destino = self.entries["Destino:"].get().strip()

        if not all([placa_cavalo, motorista]):
            messagebox.showwarning("Campos Faltando", "Placa do Cavalo e Motorista são obrigatórios.")
            return

        if weighing_type == "bruto":
            peso_bruto_str = self.entries["Peso Bruto (kg):"].get().strip()
            tipo_carga = self.entries["Tipo de Carga:"].get().strip()
            if not all([tipo_carga, peso_bruto_str]):
                messagebox.showwarning("Campos Faltando",
                                       "Para pesagem de Peso Bruto, Tipo de Carga e Peso são obrigatórios.")
                return
            try:
                peso_bruto = float(peso_bruto_str.replace(',', '.'))
                if peso_bruto <= 0:
                    messagebox.showerror("Erro de Validação", "O Peso Bruto deve ser um valor positivo.")
                    return
            except ValueError:
                messagebox.showerror("Erro de Validação", "Por favor, insira um número válido para o peso.")
                return

        else:  # weighing_type == "tara"
            peso_tara_str = self.entries["Peso Tara (kg):"].get().strip()
            if not peso_tara_str:
                messagebox.showwarning("Campos Faltando", "Para pesagem de Tara, o Peso é obrigatório.")
                return
            try:
                peso_tara = float(peso_tara_str.replace(',', '.'))
                if peso_tara <= 0:
                    messagebox.showerror("Erro de Validação", "O Peso Tara deve ser um valor positivo.")
                    return
                peso_bruto = -peso_tara
                tipo_carga = ''
            except ValueError:
                messagebox.showerror("Erro de Validação", "Por favor, insira um número válido para o peso.")
                return

        data_hora_bruto = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql = """
              INSERT INTO pesagens_pendentes (data_hora_bruto, placa, placa_carreta, motorista, origem, destino,
                                              tipo_carga, peso_bruto)
              VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
              """
        data = (data_hora_bruto, placa_cavalo, placa_carreta, motorista, origem, destino, tipo_carga, peso_bruto)

        conn = None
        try:
            conn = self.get_db_connection(show_error=True)
            if conn is None: return
            with conn.cursor() as cursor:
                cursor.execute(sql, data)
            conn.commit()

            messagebox.showinfo("Sucesso", "1ª Pesagem registada! O veículo está aguardando a saída.")
            self.limpar_campos()
            self.load_pending_weighings()
            self.notebook.select(self.pending_frame)
        except pymysql.Error as err:
            messagebox.showerror("Erro de MySQL", f"Não foi possível registar a entrada: {err}")
        finally:
            if conn:
                conn.close()

    def load_pending_weighings(self):
        for item in self.pending_tree.get_children():
            self.pending_tree.delete(item)
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None: return
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, DATE_FORMAT(data_hora_bruto, '%d/%m/%Y %H:%i:%s') as data_hora_fmt, placa, motorista, tipo_carga, peso_bruto FROM pesagens_pendentes ORDER BY id DESC")
                for row in cursor.fetchall():
                    peso_entrada = abs(row['peso_bruto'])
                    self.pending_tree.insert("", "end", values=(
                        row['id'], row['data_hora_fmt'], row['placa'], row['motorista'],
                        row['tipo_carga'], f"{peso_entrada:.2f}"
                    ))
        except pymysql.Error:
            pass
        finally:
            if conn:
                conn.close()

    def iniciar_segunda_pesagem(self):
        selected_item = self.pending_tree.focus()
        if not selected_item:
            messagebox.showwarning("Nenhuma Seleção", "Por favor, selecione um veículo da lista para registar a saída.")
            return
        pending_id = self.pending_tree.item(selected_item)['values'][0]
        conn = None
        try:
            conn = self.get_db_connection(show_error=True)
            if conn is None: return
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM pesagens_pendentes WHERE id = %s", (pending_id,))
                pending_data = cursor.fetchone()

            if pending_data:
                SegundaPesagemWindow(self, pending_id, pending_data)
            else:
                messagebox.showerror("Erro", "Este registo não foi encontrado. Pode já ter sido finalizado.")
                self.load_pending_weighings()
        except pymysql.Error as err:
            messagebox.showerror("Erro de MySQL", f"Não foi possível buscar o registo: {err}")
        finally:
            if conn:
                conn.close()

    def load_history(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        conn = None
        try:
            conn = self.get_db_connection()
            if conn is None: return
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, DATE_FORMAT(data_hora, '%d/%m/%Y %H:%i:%s') as data_hora_fmt, placa, motorista, tipo_carga, peso_liquido FROM tickets ORDER BY id DESC")
                for row in cursor.fetchall():
                    self.history_tree.insert("", "end", values=(
                        row['id'], row['data_hora_fmt'], row['placa'], row['motorista'],
                        row['tipo_carga'], f"{row['peso_liquido']:.2f}"
                    ))
        except pymysql.Error:
            pass
        finally:
            if conn:
                conn.close()

    def gerar_e_abrir_pdf(self, ticket_id):
        conn = None
        try:
            conn = self.get_db_connection(show_error=True)
            if conn is None: return
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM tickets WHERE id = %s", (ticket_id,))
                record = cursor.fetchone()

            if record is None:
                messagebox.showerror("Erro", "Ticket não encontrado no banco de dados.")
                return

            # Sanitize driver's name for filename
            motorista_nome = record.get('motorista', 'sem_nome').strip().replace(' ', '_')
            # Remove any characters that are not alphanumeric or underscore
            motorista_nome_safe = re.sub(r'[^\w_]', '', motorista_nome)

            # Format date and time for filename
            data_hora_str = record.get('data_hora').strftime("%Y%m%d_%H%M%S")

            # Create the new filename
            new_filename_base = f"{motorista_nome_safe}_{data_hora_str}.pdf"

            folder = "tickets_pdf"
            os.makedirs(folder, exist_ok=True)
            filename = os.path.join(folder, new_filename_base)
            self.criar_pdf(filename, record)
            messagebox.showinfo("Sucesso", f"PDF do ticket salvo em:\n{os.path.abspath(filename)}")

            if sys.platform == "win32":
                os.startfile(os.path.abspath(filename))
            elif sys.platform == "darwin":
                os.system(f'open "{os.path.abspath(filename)}"')
            else:
                os.system(f'xdg-open "{os.path.abspath(filename)}"')
        except pymysql.Error as err:
            messagebox.showerror("Erro de MySQL", f"Não foi possível buscar o ticket: {err}")
        except Exception as e:
            messagebox.showerror("Erro ao Gerar/Abrir PDF", f"Ocorreu um erro: {e}")
        finally:
            if conn:
                conn.close()

    def create_first_weighing_widgets(self):
        live_weight_frame = ttk.LabelFrame(self.main_frame, text="PESO ATUAL", padding=(10, 5))
        live_weight_frame.pack(fill="x", padx=5, pady=(5, 10))
        self.live_weight_label = ttk.Label(live_weight_frame, text="0.00 kg", font=("Arial", 36, "bold"),
                                           foreground="green", anchor="center")
        self.live_weight_label.pack(expand=True, fill="x", pady=5)

        weighing_type_frame = ttk.LabelFrame(self.main_frame, text="Método da 1ª Pesagem", padding=(10, 5))
        weighing_type_frame.pack(fill="x", padx=5, pady=5)
        self.weighing_type = tk.StringVar(value="bruto")
        ttk.Radiobutton(weighing_type_frame, text="Bruto Primeiro (Entrada Carregado)", variable=self.weighing_type,
                        value="bruto").pack(side="left", padx=10)
        ttk.Radiobutton(weighing_type_frame, text="Tara Primeiro (Entrada Vazio)", variable=self.weighing_type,
                        value="tara").pack(side="left", padx=10)

        self.input_frame = ttk.LabelFrame(self.main_frame, text="Registo de Entrada", padding=(10, 5))
        self.input_frame.pack(fill="x", expand=True, padx=5, pady=5)
        self.entries = {}

        common_labels = ["Placa Cavalo:", "Placa Carreta:", "Motorista:", "Origem:", "Destino:"]
        for i, text in enumerate(common_labels):
            ttk.Label(self.input_frame, text=text).grid(row=i, column=0, sticky="w", pady=6, padx=5)
            entry = ttk.Entry(self.input_frame, width=40, font=("Arial", 10))
            entry.grid(row=i, column=1, pady=6, padx=5, sticky="ew")
            self.entries[text] = entry
            if "Placa" in text:
                entry.bind("<FocusOut>", self._format_plate_entry)
                entry.bind("<KeyRelease>", self._format_plate_entry)

        self.label_tipo_carga = ttk.Label(self.input_frame, text="Tipo de Carga:")
        self.entry_tipo_carga = ttk.Entry(self.input_frame, width=40, font=("Arial", 10))
        self.entries["Tipo de Carga:"] = self.entry_tipo_carga

        self.label_peso_bruto = ttk.Label(self.input_frame, text="Peso Bruto (kg):")
        self.entry_peso_bruto = ttk.Entry(self.input_frame, width=40, font=("Arial", 10))
        self.entries["Peso Bruto (kg):"] = self.entry_peso_bruto

        self.label_peso_tara = ttk.Label(self.input_frame, text="Peso Tara (kg):")
        self.entry_peso_tara = ttk.Entry(self.input_frame, width=40, font=("Arial", 10))
        self.entries["Peso Tara (kg):"] = self.entry_peso_tara

        self.capturar_peso_button = ttk.Button(self.input_frame, text="Capturar Peso", command=self.capturar_peso)

        self.toggle_weight_entry()
        self.weighing_type.trace("w", self.toggle_weight_entry)

        self.input_frame.grid_columnconfigure(1, weight=1)

        button_frame = ttk.Frame(self.main_frame)
        button_frame.pack(pady=15)
        ttk.Button(button_frame, text="Registar Entrada", command=self.registrar_primeira_pesagem,
                   style="Success.TButton", width=20).grid(row=0, column=0, padx=10)
        ttk.Button(button_frame, text="Limpar Campos", command=self.limpar_campos, style="Warning.TButton",
                   width=20).grid(row=0, column=1, padx=10)
        self.entries["Placa Cavalo:"].focus()

    def toggle_weight_entry(self, *args):
        weighing_type = self.weighing_type.get()

        if weighing_type == "bruto":
            grid_row_for_weight = 6
            self.label_tipo_carga.grid(row=5, column=0, sticky="w", pady=6, padx=5)
            self.entry_tipo_carga.grid(row=5, column=1, pady=6, padx=5, sticky="ew")
            self.label_peso_bruto.grid(row=grid_row_for_weight, column=0, sticky="w", pady=6, padx=5)
            self.entry_peso_bruto.grid(row=grid_row_for_weight, column=1, pady=6, padx=5, sticky="ew")
            self.label_peso_tara.grid_remove()
            self.entry_peso_tara.grid_remove()
        else:  # tara
            grid_row_for_weight = 5
            self.label_tipo_carga.grid_remove()
            self.entry_tipo_carga.grid_remove()
            self.entry_tipo_carga.delete(0, tk.END)
            self.label_peso_bruto.grid_remove()
            self.entry_peso_bruto.grid_remove()
            self.label_peso_tara.grid(row=grid_row_for_weight, column=0, sticky="w", pady=6, padx=5)
            self.entry_peso_tara.grid(row=grid_row_for_weight, column=1, pady=6, padx=5, sticky="ew")

        self.capturar_peso_button.grid(row=grid_row_for_weight, column=2, padx=5, sticky="w")

    def capturar_peso(self):
        if self.balanca_reader and self.balanca_reader.is_alive():
            peso = self.balanca_reader.get_peso()
            if self.weighing_type.get() == "bruto":
                self.entries["Peso Bruto (kg):"].delete(0, tk.END)
                self.entries["Peso Bruto (kg):"].insert(0, peso)
            else:
                self.entries["Peso Tara (kg):"].delete(0, tk.END)
                self.entries["Peso Tara (kg):"].insert(0, peso)
        else:
            messagebox.showwarning("Balança", "Não foi possível ler o peso. Verifique a conexão.")

    def update_live_weight_display(self):
        if self.balanca_reader and self.balanca_reader.is_alive():
            peso = self.balanca_reader.get_peso()
            self.live_weight_label.config(text=f"{peso} kg")
            self.master.after(500, self.update_live_weight_display)
        else:
            self.live_weight_label.config(text="Balança Desconectada")
            self.master.after(2000, self.update_live_weight_display)

    def create_pending_widgets(self):
        controls_frame = ttk.Frame(self.pending_frame)
        controls_frame.pack(fill='x', pady=5)
        ttk.Button(controls_frame, text="Atualizar Lista", command=self.load_pending_weighings).pack(side="left",
                                                                                                     padx=(0, 10))
        ttk.Button(controls_frame, text="Registar Saída (2ª Pesagem)", command=self.iniciar_segunda_pesagem,
                   style="Success.TButton").pack(side="left")

        tree_frame = ttk.Frame(self.pending_frame)
        tree_frame.pack(fill="both", expand=True, pady=10)

        cols = ("ID", "Data/Hora Entrada", "Placa", "Motorista", "Carga", "Peso Entrada (kg)")
        self.pending_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", style="Treeview")

        for col in cols:
            self.pending_tree.heading(col, text=col)
        self.pending_tree.column("ID", width=50, anchor="center")
        self.pending_tree.column("Data/Hora Entrada", width=150)
        self.pending_tree.column("Peso Entrada (kg)", width=120, anchor="e")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.pending_tree.yview)
        vsb.pack(side='right', fill='y')
        self.pending_tree.configure(yscrollcommand=vsb.set)
        self.pending_tree.pack(fill="both", expand=True)
        self.pending_tree.bind("<Double-1>", lambda e: self.iniciar_segunda_pesagem())

    def create_history_widgets(self):
        controls_frame = ttk.Frame(self.history_frame)
        controls_frame.pack(fill='x', pady=5)
        ttk.Button(controls_frame, text="Atualizar Histórico", command=self.load_history).pack(side="left",
                                                                                               padx=(0, 10))
        ttk.Button(controls_frame, text="Gerar PDF do Ticket Selecionado", command=self.gerar_pdf_selecionado,
                   style="Info.TButton").pack(side="left")

        tree_frame = ttk.Frame(self.history_frame)
        tree_frame.pack(fill="both", expand=True, pady=10)

        cols = ("ID Ticket", "Data/Hora Final", "Placa", "Motorista", "Carga", "Peso Líquido (kg)")
        self.history_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", style="Treeview")

        for col in cols:
            self.history_tree.heading(col, text=col)
        self.history_tree.column("ID Ticket", width=80, anchor="center")
        self.history_tree.column("Data/Hora Final", width=150)
        self.history_tree.column("Peso Líquido (kg)", width=120, anchor="e")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.history_tree.yview)
        vsb.pack(side='right', fill='y')
        self.history_tree.configure(yscrollcommand=vsb.set)
        self.history_tree.pack(fill="both", expand=True)

    def gerar_pdf_selecionado(self):
        selected_item = self.history_tree.focus()
        if not selected_item:
            messagebox.showwarning("Nenhuma Seleção", "Por favor, selecione um ticket do histórico para gerar o PDF.")
            return
        ticket_id = self.history_tree.item(selected_item)['values'][0]
        self.gerar_e_abrir_pdf(ticket_id)

    def create_settings_widgets(self):
        container = ttk.Frame(self.settings_frame, padding=20)
        container.pack(fill='both', expand=True)

        self.settings_entries = {}
        row_num = 0

        for label_text, key in self.settings_map.items():
            ttk.Label(container, text=label_text).grid(row=row_num, column=0, sticky='w', pady=5)
            entry = ttk.Entry(container, width=50)
            entry.grid(row=row_num, column=1, sticky='ew', padx=10)
            entry.insert(0, self.app_config.get(key, ''))
            self.settings_entries[label_text] = entry

            if key == 'logopath':
                ttk.Button(container, text="Procurar...", command=self.browse_logo).grid(row=row_num, column=2)

            row_num += 1

        container.grid_columnconfigure(1, weight=1)

        save_button = ttk.Button(container, text="Salvar Configurações", command=self.save_config,
                                 style="Success.TButton")
        save_button.grid(row=row_num, column=1, pady=20, sticky='e')

    def browse_logo(self):
        filename = filedialog.askopenfilename(
            title="Selecione o arquivo de logo",
            filetypes=(("Imagens", "*.png *.jpg *.jpeg *.gif"), ("Todos os arquivos", "*.*"))
        )
        if filename:
            logo_entry = self.settings_entries.get("Caminho do Logo (opcional):")
            if logo_entry:
                logo_entry.delete(0, tk.END)
                logo_entry.insert(0, filename)

    def limpar_campos(self):
        for entry in self.entries.values():
            entry.delete(0, tk.END)
        self.entries["Placa Cavalo:"].focus()

    def _draw_ticket_content(self, c, data, start_y, title):
        # Esta função desenha o conteúdo de uma única via do ticket
        largura, _ = A4
        x_margin = 1.5 * cm
        y_pos = start_y

        # --- Cabeçalho ---
        y_pos -= 1.5 * cm
        logo_path = self.app_config.get('logopath')
        if logo_path and os.path.exists(logo_path):
            try:
                logo = ImageReader(logo_path)
                # Posiciona o logo no canto esquerdo
                c.drawImage(logo, x_margin, y_pos - 1 * cm, width=4 * cm, height=2 * cm, preserveAspectRatio=True,
                            anchor='nw')
            except Exception:
                pass

        # Informações da empresa alinhadas à direita
        c.setFont("Helvetica-Bold", 14)
        c.drawRightString(largura - x_margin, y_pos, self.app_config.get('nome', 'NOME DA EMPRESA'))
        c.setFont("Helvetica", 9)
        y_pos -= 0.5 * cm
        c.drawRightString(largura - x_margin, y_pos, f"CNPJ: {self.app_config.get('cnpj', '')}")
        y_pos -= 0.5 * cm
        c.drawRightString(largura - x_margin, y_pos, self.app_config.get('endereco', ''))
        y_pos -= 0.5 * cm
        c.drawRightString(largura - x_margin, y_pos, f"Contato: {self.app_config.get('contato', '')}")

        # --- Título ---
        y_pos -= 1 * cm
        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(largura / 2, y_pos, "TICKET DE PESAGEM")
        c.setFont("Helvetica-Oblique", 10)
        c.drawCentredString(largura / 2, y_pos - 0.5 * cm, title)
        y_pos -= 1 * cm

        # --- Informações do Ticket (ID e Data) ---
        c.setFont("Helvetica-Bold", 10)
        c.drawString(x_margin, y_pos, f"Ticket ID: {data['id']}")
        c.drawRightString(largura - x_margin, y_pos, f"Data/Hora: {data['data_hora'].strftime('%d/%m/%Y %H:%M:%S')}")
        y_pos -= 0.5 * cm
        c.line(x_margin, y_pos, largura - x_margin, y_pos)
        y_pos -= 0.7 * cm

        # --- Detalhes em Grid (2 colunas) ---
        line_height = 0.6 * cm
        col1_x = x_margin
        col2_x = x_margin + 9 * cm

        def draw_field(x, y, label, value):
            c.setFont("Helvetica-Bold", 9)
            c.drawString(x, y, label)
            c.setFont("Helvetica", 10)
            c.drawString(x + 2.5 * cm, y, str(value))

        draw_field(col1_x, y_pos, "Placa Cavalo:", data.get('placa', ''))
        draw_field(col2_x, y_pos, "Placa Carreta:", data.get('placa_carreta', 'N/A'))
        y_pos -= line_height

        draw_field(col1_x, y_pos, "Motorista:", data.get('motorista', ''))
        draw_field(col2_x, y_pos, "Tipo de Carga:", data.get('tipo_carga', ''))
        y_pos -= line_height

        draw_field(col1_x, y_pos, "Origem:", data.get('origem', ''))
        draw_field(col2_x, y_pos, "Destino:", data.get('destino', ''))

        # --- Seção de Pesos ---
        y_pos -= 1 * cm
        box_height = 3.5 * cm
        box_width = largura - (2 * x_margin)
        box_bottom_y = y_pos - box_height

        c.roundRect(x_margin, box_bottom_y, box_width, box_height, 5, stroke=1, fill=0)

        text_y = y_pos - 0.8 * cm

        c.setFont("Helvetica-Bold", 12)
        c.drawString(x_margin + 0.5 * cm, text_y, "Peso Bruto:")
        c.drawRightString(largura - x_margin - 0.5 * cm, text_y, f"{data.get('peso_bruto', 0):.2f} kg")
        text_y -= 0.8 * cm

        c.setFont("Helvetica-Bold", 12)
        c.drawString(x_margin + 0.5 * cm, text_y, "Peso Tara:")
        c.drawRightString(largura - x_margin - 0.5 * cm, text_y, f"{data.get('peso_tara', 0):.2f} kg")
        text_y -= 0.2 * cm
        c.line(x_margin + 0.5 * cm, text_y, largura - x_margin - 0.5 * cm, text_y)
        text_y -= 0.8 * cm

        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(colors.red)
        c.drawString(x_margin + 0.5 * cm, text_y, "Peso Líquido:")
        c.drawRightString(largura - x_margin - 0.5 * cm, text_y, f"{data.get('peso_liquido', 0):.2f} kg")
        c.setFillColor(colors.black)

        # --- Assinatura ---
        y_assinatura = start_y - (A4[1] / 2) + (2 * cm)
        c.line(largura / 2 - 5 * cm, y_assinatura, largura / 2 + 5 * cm, y_assinatura)
        c.setFont("Helvetica", 9)
        c.drawCentredString(largura / 2, y_assinatura - 0.4 * cm, "Assinatura do Motorista")

        # --- Modelo da Balança ---
        modelo = self.app_config.get('modelo_balanca', '')
        if modelo:
            y_modelo = start_y - (A4[1] / 2) + (1 * cm)
            c.setFont("Helvetica", 8)
            c.drawCentredString(largura / 2, y_modelo, f"Equipamento de Pesagem: {modelo}")

    def criar_pdf(self, filename, data):
        c = canvas.Canvas(filename, pagesize=A4)
        largura, altura = A4

        # Desenha a primeira via (Via da Empresa) na metade superior da página
        self._draw_ticket_content(c, data, altura, "VIA DA EMPRESA")

        # Linha divisória
        c.setDash(3, 3)  # Linha pontilhada
        c.line(1 * cm, altura / 2, largura - 1 * cm, altura / 2)
        c.setDash([], 0)  # Reseta para linha sólida

        # Desenha a segunda via (Via do Caminhoneiro) na metade inferior da página
        self._draw_ticket_content(c, data, altura / 2, "VIA DO CAMINHONEIRO")

        c.save()


if __name__ == "__main__":
    root = tk.Tk()
    app = BalancaApp(root)
    root.mainloop()