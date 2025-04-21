import os
from langchain.document_loaders import TextLoader, CSVLoader, PyPDFLoader
from langchain.document_loaders.excel import UnstructuredExcelLoader  # Para arquivos Excel
from langchain.document_loaders.unstructured import UnstructuredFileLoader  # Para formatos genéricos
from langchain.document_loaders.json_loader import JSONLoader  # Para arquivos JSON
from langchain.document_loaders.html import UnstructuredHTMLLoader  # Para arquivos HTML
from langchain.document_loaders.xml import UnstructuredXMLLoader  # Para arquivos XML
from langchain.document_loaders.email import UnstructuredEmailLoader  # Para emails
from langchain.document_loaders.word_document import UnstructuredWordDocumentLoader  # Para documentos Word
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_groq import ChatGroq
from langchain.chains import RetrievalQA
from langchain.schema.retriever import BaseRetriever
from langchain.schema import Document
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
import json
import requests
from langchain_community.vectorstores.utils import filter_complex_metadata

class DocumentProcessor:
    def __init__(self):
        load_dotenv()
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        
        # Inicializar o text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        
        # Verificar se estamos em modo de produção ou desenvolvimento
        self.is_production = self.groq_api_key and self.groq_api_key != "your_groq_api_key"
        
        # Inicializar embeddings - usamos HuggingFace em vez de OpenAI
        if self.is_production:
            try:
                # Usar modelo de embedding gratuito do HuggingFace
                self.embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-mpnet-base-v2"
                )
                print("Usando embeddings do HuggingFace em modo de produção")
            except Exception as e:
                print(f"Erro ao inicializar embeddings de produção: {e}")
                self.embeddings = self._get_mock_embeddings()
        else:
            self.embeddings = self._get_mock_embeddings()
            print("Usando embeddings simulados para desenvolvimento")
    
    def _get_mock_embeddings(self):
        """Retorna embeddings simulados para desenvolvimento"""
        class MockEmbeddings:
            def embed_documents(self, texts):
                # Retorna embeddings simulados (vetores de dimensão 5)
                return [[0.1, 0.2, 0.3, 0.4, 0.5] for _ in texts]
            
            def embed_query(self, text):
                # Retorna embedding simulado para a query
                return [0.1, 0.2, 0.3, 0.4, 0.5]
        
        return MockEmbeddings()
    
    def _get_groq_llm(self):
        """Configura e retorna o LLM do GroqCloud"""
        if not self.is_production:
            # Mock LLM para desenvolvimento
            class MockLLM:
                def invoke(self, prompt):
                    return f"Resposta simulada para: {prompt}"
            return MockLLM()
            
        try:
            # Usar ChatGroq da langchain_groq
            llm = ChatGroq(
                api_key=self.groq_api_key,
                model="llama3-8b-8192"  # ou outro modelo disponível no GroqCloud
            )
            return llm
        except Exception as e:
            print(f"Erro ao inicializar LLM Groq: {e}")
            # Retornar mock LLM em caso de erro
            class FallbackMockLLM:
                def invoke(self, prompt):
                    return f"Não foi possível conectar ao GroqCloud. Resposta simulada para: {prompt}"
            return FallbackMockLLM()
    
    def load_document(self, file_path):
        """Carrega um documento com base em sua extensão"""
        file_extension = os.path.splitext(file_path)[1].lower()
        
        try:
            # Loaders específicos para formatos comuns
            if file_extension == '.txt':
                loader = TextLoader(file_path)
            elif file_extension == '.csv':
                loader = CSVLoader(file_path)
            elif file_extension == '.pdf':
                loader = PyPDFLoader(file_path)
            elif file_extension in ['.xlsx', '.xls']:
                # Usar loader específico para Excel
                loader = UnstructuredExcelLoader(file_path, mode="elements")
            elif file_extension in ['.docx', '.doc']:
                # Loader para documentos Word
                loader = UnstructuredWordDocumentLoader(file_path)
            elif file_extension == '.json':
                # Definir uma função para extrair o conteúdo de cada item do JSON
                def metadata_func(record, metadata):
                    metadata["content"] = record.get("content", "")
                    return metadata
                
                loader = JSONLoader(
                    file_path=file_path,
                    jq_schema='.[]',  # Ajuste conforme a estrutura do seu JSON
                    content_key="content",  # Chave que contém o texto principal
                    metadata_func=metadata_func
                )
            elif file_extension in ['.html', '.htm']:
                loader = UnstructuredHTMLLoader(file_path)
            elif file_extension == '.xml':
                loader = UnstructuredXMLLoader(file_path)
            elif file_extension in ['.eml', '.msg']:
                loader = UnstructuredEmailLoader(file_path)
            else:
                # Tentar usar um loader genérico para outros tipos
                print(f"Tentando usar loader genérico para o formato: {file_extension}")
                loader = UnstructuredFileLoader(file_path)
            
            # Carregar os documentos
            documents = loader.load()
            
            if not documents:
                print(f"Aviso: Nenhum conteúdo extraído do arquivo {file_path}")
            else:
                print(f"Documento carregado com sucesso: {len(documents)} elementos")
            
            return documents
        except Exception as e:
            print(f"Erro ao carregar documento ({file_extension}): {e}")
            # Tentar usar o loader genérico como fallback
            try:
                print("Tentando usar loader genérico como fallback...")
                loader = UnstructuredFileLoader(file_path)
                return loader.load()
            except Exception as fallback_error:
                print(f"Erro no fallback: {fallback_error}")
                return None
    
    def process_document(self, file_path):
        """Processa um documento e retorna os chunks"""
        documents = self.load_document(file_path)
        if not documents:
            return None
        
        # Filtrar metadados complexos para evitar erros ao criar a vector store
        for doc in documents:
            if hasattr(doc, 'metadata'):
                doc.metadata = self._filter_metadata(doc.metadata)
        
        # Dividir documentos em chunks
        chunks = self.text_splitter.split_documents(documents)
        return chunks
    
    def _filter_metadata(self, metadata):
        """Filtra metadados complexos para evitar erros no Chroma"""
        filtered_metadata = {}
        for key, value in metadata.items():
            # Aceitar apenas tipos simples: str, int, float, bool
            if isinstance(value, (str, int, float, bool)):
                filtered_metadata[key] = value
            elif isinstance(value, list):
                # Para listas, converter para string
                filtered_metadata[key] = str(value)
            elif isinstance(value, dict):
                # Para dicionários, converter para string JSON
                try:
                    filtered_metadata[key] = json.dumps(value)
                except:
                    filtered_metadata[key] = str(value)
            else:
                # Para outros tipos complexos, converter para string
                filtered_metadata[key] = str(value)
        return filtered_metadata
    
    def create_vector_store(self, chunks, collection_name="document_collection"):
        """Cria uma vector store a partir dos chunks"""
        if not chunks:
            print("Aviso: Nenhum chunk fornecido para criar a vector store")
            return self._create_mock_vector_store([], collection_name)
        
        # Filtrar metadados complexos de todos os chunks
        filtered_chunks = []
        for chunk in chunks:
            # Converter para Document se não for
            if not isinstance(chunk, Document):
                chunk_doc = Document(
                    page_content=chunk.page_content if hasattr(chunk, 'page_content') else str(chunk),
                    metadata=self._filter_metadata(chunk.metadata) if hasattr(chunk, 'metadata') else {}
                )
                filtered_chunks.append(chunk_doc)
            else:
                # Filtrar metadados complexos
                chunk.metadata = self._filter_metadata(chunk.metadata)
                filtered_chunks.append(chunk)
        
        if self.is_production and filtered_chunks:
            try:
                # Usar Chroma como vector store
                vector_store = Chroma.from_documents(
                    documents=filtered_chunks, 
                    embedding=self.embeddings,
                    collection_name=collection_name
                )
                print(f"Vector store criada com {len(filtered_chunks)} chunks")
                return vector_store
            except Exception as e:
                print(f"Erro ao criar vector store: {e}")
                return self._create_mock_vector_store(filtered_chunks, collection_name)
        else:
            return self._create_mock_vector_store(filtered_chunks, collection_name)
    
    def _create_mock_vector_store(self, chunks, collection_name):
        """Cria uma vector store simulada para desenvolvimento"""
        print(f"Simulando criação de vector store com {len(chunks)} chunks")
        
        # Implementação de MockRetriever que herda de BaseRetriever
        class MockRetriever(BaseRetriever):
            def __init__(self, chunks):
                self.chunks = chunks
                
            def get_relevant_documents(self, query):
                # Retorna alguns chunks como se fossem os mais relevantes
                return self.chunks[:2] if self.chunks else []
                
            async def aget_relevant_documents(self, query):
                # Implementação assíncrona necessária
                return self.get_relevant_documents(query)
        
        # Implementação de MockVectorStore
        class MockVectorStore:
            def __init__(self, chunks):
                self.chunks = chunks
                
            def as_retriever(self, **kwargs):
                return MockRetriever(self.chunks)
                
        return MockVectorStore(chunks)
    
    def query_document(self, query, vector_store):
        """Consulta o documento usando LangChain"""
        if not vector_store:
            return "Erro: Vector store não inicializada corretamente."
        
        if self.is_production:
            try:
                # Configurar LLM do GroqCloud
                llm = self._get_groq_llm()
                
                # Criar chain para consulta de documentos
                qa_chain = RetrievalQA.from_chain_type(
                    llm=llm,
                    chain_type="stuff",
                    retriever=vector_store.as_retriever()
                )
                
                # Executar consulta
                result = qa_chain.invoke({"query": query})
                
                # Formatar o resultado - depende da estrutura de retorno do LLM/Chain
                if isinstance(result, dict) and "result" in result:
                    return result["result"]
                return str(result)
            except Exception as e:
                print(f"Erro ao consultar documento com GroqCloud: {e}")
                return f"Erro ao processar consulta: {str(e)}"
        else:
            # Simular consulta para desenvolvimento
            print(f"Simulando consulta: '{query}' na vector store")
            result = f"Resposta simulada para a consulta: '{query}'. Esta resposta está baseada nos dados do documento."
            return result
    
    def get_document_metadata(self, file_path):
        """Retorna metadados do documento"""
        try:
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)
            file_extension = os.path.splitext(file_path)[1].lower()
            
            metadata = {
                "file_name": file_name,
                "file_extension": file_extension,
                "file_size": file_size,
                "file_path": file_path
            }
            
            # Adicionar informações específicas baseadas no tipo de arquivo
            if file_extension in ['.xlsx', '.xls']:
                metadata["type"] = "Excel spreadsheet"
            elif file_extension in ['.docx', '.doc']:
                metadata["type"] = "Word document"
            elif file_extension == '.pdf':
                metadata["type"] = "PDF document"
            elif file_extension == '.txt':
                metadata["type"] = "Text file"
            elif file_extension == '.csv':
                metadata["type"] = "CSV data"
            elif file_extension in ['.html', '.htm']:
                metadata["type"] = "HTML document"
            elif file_extension == '.json':
                metadata["type"] = "JSON data"
            elif file_extension == '.xml':
                metadata["type"] = "XML document"
            else:
                metadata["type"] = "Unknown format"
                
            return metadata
        except Exception as e:
            print(f"Erro ao obter metadados: {e}")
            return None
    
    def generate_embeddings(self, texts):
        """Gera embeddings para textos"""
        if self.is_production:
            try:
                return self.embeddings.embed_documents(texts)
            except Exception as e:
                print(f"Erro ao gerar embeddings: {e}")
                return [[0.0] * 5 for _ in texts]  # Fallback para embeddings vazios
        else:
            # Retornar embeddings simulados
            return [[0.1, 0.2, 0.3, 0.4, 0.5] for _ in texts]