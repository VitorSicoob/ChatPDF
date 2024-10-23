import os

from dotenv import load_dotenv
import streamlit as st
from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_text_splitters.character import CharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain

load_dotenv()

working_dir = os.path.dirname(os.path.abspath(__file__))

def load_documents(file_paths):
    documents = []
    for file_path in file_paths:
        loader = UnstructuredPDFLoader(file_path)
        documents.extend(loader.load())
    return documents

def setup_vectorstore(documents):
    embeddings = HuggingFaceEmbeddings()
    text_splitter = CharacterTextSplitter(
        separator="/n",
        chunk_size=1000,
        chunk_overlap=200
    )

    doc_chunks = text_splitter.split_documents(documents)
    vectorstore = FAISS.from_documents(doc_chunks, embeddings)
    return vectorstore

def create_chain(vectorstore):
    llm = ChatGroq(
        model="llama-3.1-70b-versatile",
        temperature=0
    )
    retriever = vectorstore.as_retriever()
    memory = ConversationBufferMemory(
        llm=llm,
        output_key="answer",
        memory_key="chat_history",
        return_messages=True
    )
    chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=retriever,
        memory=memory,
        verbose=True
    )
    return chain

st.set_page_config(
    page_title="ChatPDF",
    page_icon="💚",
    layout="centered"

)

with st.sidebar:
    st.markdown('''
    ## Sobre 
    Esse aplicativo utiliza LLM e foi criado usando:
    - [Streamlit](https://streamlit.io/)
    - [LangChain](https://python.langchain.com/)
    - [HuggingFace](https://huggingface.co/)
    - [Groq](https://console.groq.com/docs/models) 
    
    ''')
    st.write('Feito por [Bruno F.](https://github.com/Brunof-Sicoob) 💚')

st.image("sicoob-logo-6.png")
st.title("Converse com o seu :red[Arquivo PDF] - :green[LLAMA 3.1] 🦙")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


uploaded_files = st.file_uploader(label="Faça Upload dos seus PDFs", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    file_paths = []
    for uploaded_file in uploaded_files:
        file_path = f"{working_dir}/{uploaded_file.name}"
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        file_paths.append(file_path)
        

    if "vectorstore" not in st.session_state:
        documents = load_documents(file_paths)
        st.session_state.vectorstore = setup_vectorstore(documents)

    if "conversation_chain" not in st.session_state:
        st.session_state.conversation_chain = create_chain(st.session_state.vectorstore)

for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_input = st.chat_input("Pergunte ao Llama...")

if user_input:
    st.session_state.chat_history.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        response = st.session_state.conversation_chain({"question": user_input})
        assistant_response = response["answer"]
        st.markdown(assistant_response)
        st.session_state.chat_history.append({"role": "user", "content": assistant_response})

