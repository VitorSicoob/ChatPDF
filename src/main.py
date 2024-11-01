import os
import sqlite3
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

# Carregando as variáveis de ambiente
load_dotenv()
groq_api_key = os.getenv('GROQ_API_KEY')

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'src/img'
app.config['SECRET_KEY'] = 'supersecretkey'
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
    text_splitter = CharacterTextSplitter(separator="\n", chunk_size=3000, chunk_overlap=50)
    doc_chunks = text_splitter.split_documents(documents)
    vectorstore = FAISS.from_documents(doc_chunks, embeddings)
    return vectorstore


def create_chain(vectorstore):
    llm = ChatGroq(
        model="llama-3.1-70b-versatile",
        temperature=0,
        api_key=groq_api_key  # passando a chave API aqui
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
                file_path = f"{working_dir}/{file.filename}"
                file.save(file_path)
                file_paths.append(file_path)
            documents = load_documents(file_paths)
            vectorstore = setup_vectorstore(documents)
            app.config['vectorstore'] = vectorstore
            app.config['conversation_chain'] = create_chain(vectorstore)
            session['chat_history'] = []  # inicializa o histórico de conversas na sessão
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

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO chat_history (user_input, assistant_response) VALUES (?, ?)
        ''', (user_input, assistant_response))

        # consulta última linha 
        cursor.execute("SELECT assistant_response FROM chat_history ORDER BY id DESC LIMIT 1")
        ultima_linha = cursor.fetchone()

        if ultima_linha:
            print("Última linha da coluna: ", ultima_linha[0])
        else:
            print("Nenhuma linha encontrada")
        conn.commit()
        conn.close()

    return render_template('chat.html', chat_history=session['chat_history'])

if __name__ == '__main__':
    app.run(debug=True)
