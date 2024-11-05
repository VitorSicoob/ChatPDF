import os
import sqlite3
import pandas as pd
import win32com.client as win32
from dotenv import load_dotenv
from flask import Flask, request, render_template, redirect, url_for, send_from_directory, session
from flask_session import Session
from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_text_splitters.character import CharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain
from openpyxl import load_workbook
import locale
import pythoncom
import tkinter as tk
from tkinter import messagebox
 
# Carregando as variáveis de ambiente
load_dotenv()
groq_api_key = os.getenv('GROQ_API_KEY')
 
if not groq_api_key:
    raise ValueError("A variável de ambiente 'GROQ_API_KEY' não está definida.")
 
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'src/img'
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'supersecretkey')  # Carregar a chave secreta de uma variável de ambiente
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)
 
working_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(working_dir, 'chat_data.db')
 
# Função para inicializar o banco de dados
def init_db():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_input TEXT NOT NULL,
            assistant_response TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
 
# Inicializando o banco de dados
init_db()
 
@app.route('/src/img/<path:filename>')
def send_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
 
def load_documents(file_paths):
    documents = []
    for file_path in file_paths:
        loader = UnstructuredPDFLoader(file_path)
        documents.extend(loader.load())
    return documents
 
def setup_vectorstore(documents):
    embeddings = HuggingFaceEmbeddings()
    text_splitter = CharacterTextSplitter(separator="\n", chunk_size=1000, chunk_overlap=200)
    doc_chunks = text_splitter.split_documents(documents)
    vectorstore = FAISS.from_documents(doc_chunks, embeddings)
    return vectorstore
 
def create_chain(vectorstore):
    llm = ChatGroq(
        model="llama-3.1-70b-versatile",
        temperature=0,
        api_key=groq_api_key
    )
    retriever = vectorstore.as_retriever()
    memory = ConversationBufferMemory(llm=llm, output_key="answer", memory_key="chat_history", return_messages=True)
    chain = ConversationalRetrievalChain.from_llm(llm=llm, retriever=retriever, memory=memory, verbose=True)
    return chain
 
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        files = request.files.getlist('file')
        if files:
            file_paths = []
            for file in files:
                file_path = os.path.join(working_dir, file.filename)
                file.save(file_path)
                file_paths.append(file_path)
            documents = load_documents(file_paths)
            vectorstore = setup_vectorstore(documents)
            app.config['vectorstore'] = vectorstore
            app.config['conversation_chain'] = create_chain(vectorstore)
            session['chat_history'] = []
            return redirect(url_for('chat'))
    return render_template('index.html')
 
@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'conversation_chain' not in app.config:
        return redirect(url_for('index'))
 
    if 'chat_history' not in session:
        session['chat_history'] = []
 
    if request.method == 'POST':
        user_input = request.form['user_input']
        session['chat_history'].append({'role': 'voce', 'content': user_input})
        response = app.config['conversation_chain']({'question': user_input})
        assistant_response = response['answer']
        session['chat_history'].append({'role': 'assistente', 'content': assistant_response})
 
        # Salvando no banco de dados
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO chat_history (user_input, assistant_response) VALUES (?, ?)
            ''', (user_input, assistant_response))
            conn.commit()
        except sqlite3.Error as e:
            print(f"Erro ao salvar no banco de dados: {e}")
        finally:
            conn.close()
 
    return render_template('chat.html', chat_history=session['chat_history'])
 
def export_to_excel():
    """Export the last entry from the database to a uniquely named Excel file."""
    base_filename = "dados"
    file_extension = ".xlsx"
    excel_file_path = os.path.join(working_dir, f"{base_filename}{file_extension}")
   
    # Garante que o arquivo tenha um nome único
    counter = 1
    while os.path.exists(excel_file_path):
        excel_file_path = os.path.join(working_dir, f"{base_filename}{counter}{file_extension}")
        counter += 1
 
    conn = None
    try:
        conn = sqlite3.connect(db_path)
       
        # Consulta para obter a última entrada
        df = pd.read_sql_query("SELECT assistant_response FROM chat_history ORDER BY id DESC LIMIT 1", conn)
 
        # Define a localidade para português do Brasil
        locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
 
        # Exporta para Excel
        df.to_excel(excel_file_path, index=False, engine='openpyxl')
 
        # Carregando o arquivo e formatando
        wb = load_workbook(excel_file_path)
        ws = wb.active
 
        # Ajustando a largura das colunas e habilitando quebra de linha
        for col in ws.columns:
            max_length = 0
            column = col[0].column_letter  # Obter a letra da coluna
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = (max_length + 2)  # Adiciona um pouco de espaço
            ws.column_dimensions[column].width = adjusted_width
            for cell in col:
                cell.alignment = cell.alignment.copy(wrap_text=True)  # Habilita quebra de linha
 
        wb.save(excel_file_path)  # Salva as alterações no arquivo
 
        return excel_file_path  # Retorna o caminho do arquivo gerado
    except Exception as e:
        print(f"Erro ao exportar para Excel: {e}")
        return None
    finally:
        if conn:
            conn.close()
 
def send_email_with_attachment(file_path, recipients):
    try:
        # Verifica se o arquivo existe
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"O arquivo {file_path} não foi encontrado.")
 
        # Inicializa o COM
        pythoncom.CoInitialize()
       
        outlook = win32.Dispatch('outlook.application')
        mail = outlook.CreateItem(0)
 
        mail.Subject = 'Histórico de Chats'
        mail.Body = 'Segue em anexo o histórico de chats.'
        mail.To = '; '.join(recipients)  # Adiciona múltiplos destinatários
 
        mail.Attachments.Add(file_path)
        mail.Send()
       
    except FileNotFoundError as fnf_error:
        print(f"Erro ao enviar email: {fnf_error}")
    except Exception as e:
        print(f"Erro ao enviar email: {e}")
    finally:
        # Desinicializa o COM
        pythoncom.CoUninitialize()
 
class EmailSenderApp:
    def __init__(self, master, file_path):
        self.master = master
        self.file_path = file_path
        master.title("Enviar Email")
 
        self.label = tk.Label(master, text="Digite os emails separados por vírgula:")
        self.label.pack()
 
        self.email_entry = tk.Entry(master, width=50)
        self.email_entry.pack()
 
        self.send_button = tk.Button(master, text="Enviar Email", command=self.send_email)
        self.send_button.pack()
 
        self.status_label = tk.Label(master, text="")
        self.status_label.pack()
 
    def send_email(self):
        recipients = self.email_entry.get().split(',')
        recipients = [email.strip() for email in recipients if email.strip()]  # Remove espaços em branco
 
        if self.file_path:
            send_email_with_attachment(self.file_path, recipients)  # Envia email
            self.status_label.config(text="Email enviado com sucesso!")
        else:
            self.status_label.config(text="Erro ao exportar o arquivo Excel.")
 
@app.route('/export', methods=['GET'])
def export():
    excel_file = export_to_excel()  # Exporta dados para Excel
    if excel_file:
        # Inicia a interface de envio de email apenas após a exportação
        root = tk.Tk()
        root.withdraw()  # Oculta a janela principal
 
        # Inicia a interface de envio de email
        email_sender_app = EmailSenderApp(root, excel_file)
        root.deiconify()  # Mostra a janela
        root.mainloop()
        return "Operação de envio de email concluída!"
    else:
        return "Erro ao exportar o arquivo Excel."
 
if __name__ == '__main__':
    app.run(debug=False)