import streamlit as st
import os
import tempfile
from document_processor import DocumentProcessor
from database_manager import DatabaseManager
import pandas as pd
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Inicializar processador de documentos e gerenciador de banco de dados
document_processor = DocumentProcessor()
db_manager = DatabaseManager()

# Inicializar banco de dados
db_manager.initialize_database()

def main():
    st.set_page_config(page_title="Agente LangChain - Processador de Arquivos", layout="wide")
    
    st.title("Agente LangChain - Processador de Arquivos")
    st.subheader("Armazenamento em PostgreSQL (Neon)")
    
    # Barra lateral com opções
    st.sidebar.title("Navegação")
    page = st.sidebar.radio("Selecione uma opção", [
        "Upload de Arquivos", 
        "Visualizar Documentos", 
        "Consultar Documentos",
        "Sobre o Agente"
    ])
    
    # Exibir página selecionada
    if page == "Upload de Arquivos":
        upload_page()
    elif page == "Visualizar Documentos":
        view_documents_page()
    elif page == "Consultar Documentos":
        query_documents_page()
    elif page == "Sobre o Agente":
        about_page()

def upload_page():
    st.header("Upload de Arquivos")
    st.write("Faça upload de arquivos para processamento e armazenamento no banco de dados.")
    
    # Adicionar state para controlar fluxo
    if 'file_processed' not in st.session_state:
        st.session_state.file_processed = False
    if 'chunks' not in st.session_state:
        st.session_state.chunks = None
    
    # Atualizar tipos de arquivo suportados
    supported_types = ["txt", "csv", "pdf", "xlsx", "xls", "docx", "doc", "json", "html", "htm", "xml", "eml", "msg"]
    uploaded_file = st.file_uploader("Escolha um arquivo", type=supported_types)
    
    if uploaded_file is not None:
        # Exibir informações do arquivo
        file_details = {
            "Nome do arquivo": uploaded_file.name,
            "Tipo de arquivo": uploaded_file.type,
            "Tamanho": f"{uploaded_file.size} bytes"
        }
        
        st.write("### Detalhes do Arquivo")
        for key, value in file_details.items():
            st.write(f"**{key}:** {value}")
        
        # Salvar arquivo temporariamente para processamento
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            temp_file_path = tmp_file.name
        
        # Função para processar o arquivo e armazenar resultado na session_state
        def process_file():
            with st.spinner("Processando arquivo..."):
                try:
                    # Processar documento
                    st.session_state.chunks = document_processor.process_document(temp_file_path)
                    if st.session_state.chunks:
                        st.session_state.file_processed = True
                    else:
                        st.error("Não foi possível extrair conteúdo do arquivo.")
                except Exception as e:
                    st.error(f"Erro ao processar arquivo: {str(e)}")
                finally:
                    # Remover arquivo temporário
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
        
        # Botão para processar
        if not st.session_state.file_processed:
            if st.button("Processar Arquivo"):
                process_file()
        
        # Mostrar resultados do processamento se já processado
        if st.session_state.file_processed and st.session_state.chunks:
            st.success(f"Arquivo processado com sucesso! Dividido em {len(st.session_state.chunks)} chunks.")
            
            # Mostrar prévia dos chunks
            st.write("### Prévia dos Chunks")
            for i, chunk in enumerate(st.session_state.chunks[:3]):  # Mostrar apenas os 3 primeiros chunks
                with st.expander(f"Chunk {i+1}"):
                    st.write(chunk.page_content[:500] + "..." if len(chunk.page_content) > 500 else chunk.page_content)
            
            # Função para armazenar no banco de dados
            def store_in_db():
                # Armazenar documento
                doc_id = db_manager.store_document(
                    filename=uploaded_file.name,
                    file_type=uploaded_file.type,
                    file_size=uploaded_file.size,
                    metadata={"source": "upload"}
                )
                
                if doc_id:
                    # Armazenar chunks
                    success = db_manager.store_document_chunks(doc_id, st.session_state.chunks)
                    
                    if success:
                        st.success(f"Documento armazenado com sucesso! ID: {doc_id}")
                        # Resetar o estado para permitir novo processamento
                        st.session_state.file_processed = False
                        st.session_state.chunks = None
                    else:
                        st.error("Erro ao armazenar chunks do documento.")
                else:
                    st.error("Erro ao armazenar documento no banco de dados.")
            
            # Botão para armazenar
            if st.button("Armazenar no Banco de Dados"):
                store_in_db()


def view_documents_page():
    st.header("Visualizar Documentos")
    st.write("Visualize os documentos armazenados no banco de dados.")
    
    # Listar documentos
    documents = db_manager.list_documents()
    
    if not documents:
        st.info("Nenhum documento encontrado no banco de dados.")
    else:
        # Criar DataFrame para exibição
        df_data = []
        for doc in documents:
            df_data.append({
                "ID": doc["id"],
                "Nome do Arquivo": doc["filename"],
                "Tipo": doc["file_type"],
                "Tamanho (bytes)": doc["file_size"],
                "Data de Upload": doc["upload_date"]
            })
        
        df = pd.DataFrame(df_data)
        st.dataframe(df)
        
        # Selecionar documento para visualizar chunks
        if documents:
            doc_id = st.selectbox("Selecione um documento para visualizar os chunks", 
                                 options=[doc["id"] for doc in documents],
                                 format_func=lambda x: f"ID: {x} - {next((doc['filename'] for doc in documents if doc['id'] == x), '')}")
            
            if st.button("Visualizar Chunks"):
                chunks = db_manager.get_document_chunks(doc_id)
                
                if not chunks:
                    st.info("Nenhum chunk encontrado para este documento.")
                else:
                    st.write(f"### Chunks do Documento (Total: {len(chunks)})")
                    for chunk in chunks:
                        with st.expander(f"Chunk {chunk['chunk_index'] + 1}"):
                            st.write(chunk["chunk_text"])
            
            # Opção para excluir documento
            if st.button("Excluir Documento", key="delete_btn"):
                if db_manager.delete_document(doc_id):
                    st.success(f"Documento ID {doc_id} excluído com sucesso!")
                    st.experimental_rerun()  # Recarregar a página
                else:
                    st.error("Erro ao excluir documento.")

def query_documents_page():
    st.header("Consultar Documentos")
    st.write("Faça consultas nos documentos armazenados usando LangChain.")
    
    # Listar documentos
    documents = db_manager.list_documents()
    
    if not documents:
        st.info("Nenhum documento encontrado no banco de dados para consulta.")
    else:
        # Selecionar documento para consulta
        doc_id = st.selectbox("Selecione um documento para consultar", 
                             options=[doc["id"] for doc in documents],
                             format_func=lambda x: f"ID: {x} - {next((doc['filename'] for doc in documents if doc['id'] == x), '')}")
        
        # Campo de consulta
        query = st.text_input("Digite sua consulta:")
        
        if query and st.button("Consultar"):
            with st.spinner("Processando consulta..."):
                # Em um ambiente real, recuperaríamos os chunks e embeddings do banco de dados
                # e usaríamos para criar uma vector store para consulta
                
                # Simulação para desenvolvimento
                chunks = db_manager.get_document_chunks(doc_id)
                
                if chunks:
                    # Simular criação de vector store
                    mock_vector_store = document_processor.create_vector_store([
                        type('obj', (object,), {
                            'page_content': chunk["chunk_text"],
                            'metadata': chunk.get("metadata", {})
                        }) for chunk in chunks
                    ])
                    
                    # Simular consulta
                    result = document_processor.query_document(query, mock_vector_store)
                    
                    # Armazenar consulta no banco de dados
                    db_manager.store_query(query, doc_id, result)
                    
                    # Exibir resultado
                    st.write("### Resultado da Consulta")
                    st.info(result)
                else:
                    st.error("Não foi possível recuperar os chunks do documento para consulta.")

def about_page():
    st.header("Sobre o Agente LangChain")
    
    st.write("""
    ### Descrição
    Este é um agente desenvolvido com Python e LangChain para processamento de arquivos e armazenamento em banco de dados PostgreSQL (Neon).
    
    ### Funcionalidades
    - Upload e processamento de diferentes tipos de arquivos (TXT, CSV, PDF, XLSX)
    - Divisão de documentos em chunks para processamento eficiente
    - Armazenamento de documentos e chunks em banco de dados PostgreSQL
    - Consulta de documentos usando LangChain e modelos de linguagem
    - Visualização e gerenciamento de documentos armazenados
    
    ### Tecnologias Utilizadas
    - **Python**: Linguagem de programação principal
    - **LangChain**: Framework para desenvolvimento de aplicações com LLMs
    - **Streamlit**: Interface de usuário interativa
    - **PostgreSQL (Neon)**: Banco de dados para armazenamento
    - **OpenAI**: Modelos de linguagem para processamento de consultas
    
    ### Modo de Desenvolvimento
    Este agente está configurado para funcionar em modo simulado, permitindo o desenvolvimento e teste sem necessidade de credenciais reais de banco de dados ou API.
    """)

if __name__ == "__main__":
    main()
