import os
from dotenv import load_dotenv
from flask import Flask, request, render_template, redirect, url_for
from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_text_splitters.character import CharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain

load_dotenv()
groq_api_key = os.getenv('GROQ_API_KEY')

app = Flask(__name__)
working_dir = os.path.dirname(os.path.abspath(__file__))

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
        api_key=groq_api_key  # Passando a chave API aqui
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
            if 'vectorstore' not in app.config:
                documents = load_documents(file_paths)
                app.config['vectorstore'] = setup_vectorstore(documents)
            if 'conversation_chain' not in app.config:
                app.config['conversation_chain'] = create_chain(app.config['vectorstore'])
            return redirect(url_for('chat'))
    return render_template('index.html')

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    chat_history = []
    if request.method == 'POST':
        user_input = request.form['user_input']
        chat_history.append({'role': 'user', 'content': user_input})
        response = app.config['conversation_chain']({'question': user_input})
        assistant_response = response['answer']
        chat_history.append({'role': 'assistant', 'content': assistant_response})
    return render_template('chat.html', chat_history=chat_history)

if __name__ == '__main__':
    app.run(debug=True)
