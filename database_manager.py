import psycopg2
import json
import os
from dotenv import load_dotenv
from datetime import datetime

class DatabaseManager:
    def __init__(self):
        load_dotenv()
        self.db_host = os.getenv("NEON_DB_HOST")
        self.db_port = os.getenv("NEON_DB_PORT")
        self.db_name = os.getenv("NEON_DB_NAME")
        self.db_user = os.getenv("NEON_DB_USER")
        self.db_password = os.getenv("NEON_DB_PASSWORD")
        
        
        # Flag para modo simulado
        self.mock_mode = True if self.db_host == "db.mockserver.neon.tech" else False
        
        # Inicializar armazenamento simulado para desenvolvimento
        if self.mock_mode:
            self.mock_documents = []
            self.mock_chunks = []
            self.mock_document_id_counter = 1
            self.mock_chunk_id_counter = 1
    
    def connect(self):
        """Estabelece conexão com o banco de dados PostgreSQL"""
        if self.mock_mode:
            print("Usando conexão simulada para desenvolvimento")
            return None
        
        try:
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_password
            )
            return conn
        except Exception as e:
            print(f"Erro ao conectar ao banco de dados: {e}")
            return None
    
    def initialize_database(self):
        """Cria as tabelas necessárias no banco de dados"""
        if self.mock_mode:
            print("Simulando inicialização do banco de dados")
            return True
        
        conn = self.connect()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            
            
            # Tabela para documentos
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB
            )
            """)
            
            # Tabela para chunks de documentos
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
                chunk_text TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                embedding VECTOR(1536),
                metadata JSONB
            )
            """)
            
            # Tabela para consultas
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS queries (
                id SERIAL PRIMARY KEY,
                query_text TEXT NOT NULL,
                document_id INTEGER REFERENCES documents(id),
                result_text TEXT,
                query_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"Erro ao inicializar banco de dados: {e}")
            if conn:
                conn.close()
            return False
    
    def store_document(self, filename, file_type, file_size, metadata=None):
        """Armazena metadados do documento no banco de dados"""
        if self.mock_mode:
            doc_id = self.mock_document_id_counter
            self.mock_document_id_counter += 1
            
            doc = {
                "id": doc_id,
                "filename": filename,
                "file_type": file_type,
                "file_size": file_size,
                "upload_date": datetime.now().isoformat(),
                "metadata": metadata or {}
            }
            
            self.mock_documents.append(doc)
            print(f"Documento simulado armazenado com ID: {doc_id}")
            return doc_id
        
        conn = self.connect()
        if not conn:
            return None
        
        try:
            cursor = conn.cursor()
            
            metadata_json = json.dumps(metadata) if metadata else '{}'
            
            cursor.execute(
                "INSERT INTO documents (filename, file_type, file_size, metadata) VALUES (%s, %s, %s, %s) RETURNING id",
                (filename, file_type, file_size, metadata_json)
            )
            
            document_id = cursor.fetchone()[0]
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return document_id
        except Exception as e:
            print(f"Erro ao armazenar documento: {e}")
            if conn:
                conn.close()
            return None
    
    def store_document_chunks(self, document_id, chunks, embeddings=None):
        """Armazena chunks de documento no banco de dados"""
        if self.mock_mode:
            for i, chunk in enumerate(chunks):
                chunk_id = self.mock_chunk_id_counter
                self.mock_chunk_id_counter += 1
                
                chunk_data = {
                    "id": chunk_id,
                    "document_id": document_id,
                    "chunk_text": chunk.page_content if hasattr(chunk, 'page_content') else str(chunk),
                    "chunk_index": i,
                    "metadata": chunk.metadata if hasattr(chunk, 'metadata') else {}
                }
                
                self.mock_chunks.append(chunk_data)
            
            print(f"Armazenados {len(chunks)} chunks simulados para o documento {document_id}")
            return True
        
        conn = self.connect()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            
            for i, chunk in enumerate(chunks):
                chunk_text = chunk.page_content if hasattr(chunk, 'page_content') else str(chunk)
                chunk_metadata = json.dumps(chunk.metadata) if hasattr(chunk, 'metadata') else '{}'
                
                # Se embeddings estiverem disponíveis, armazená-los
                if embeddings and i < len(embeddings):
                    cursor.execute(
                        "INSERT INTO document_chunks (document_id, chunk_text, chunk_index, embedding, metadata) VALUES (%s, %s, %s, %s, %s)",
                        (document_id, chunk_text, i, embeddings[i], chunk_metadata)
                    )
                else:
                    cursor.execute(
                        "INSERT INTO document_chunks (document_id, chunk_text, chunk_index, metadata) VALUES (%s, %s, %s, %s)",
                        (document_id, chunk_text, i, chunk_metadata)
                    )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
        except Exception as e:
            print(f"Erro ao armazenar chunks: {e}")
            if conn:
                conn.close()
            return False
    
    def get_document(self, document_id):
        """Recupera informações de um documento específico"""
        if self.mock_mode:
            for doc in self.mock_documents:
                if doc["id"] == document_id:
                    return doc
            return None
        
        conn = self.connect()
        if not conn:
            return None
        
        try:
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, filename, file_type, file_size, upload_date, metadata FROM documents WHERE id = %s",
                (document_id,)
            )
            
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                return {
                    "id": result[0],
                    "filename": result[1],
                    "file_type": result[2],
                    "file_size": result[3],
                    "upload_date": result[4],
                    "metadata": result[5]
                }
            else:
                return None
        except Exception as e:
            print(f"Erro ao recuperar documento: {e}")
            if conn:
                conn.close()
            return None
    
    def get_document_chunks(self, document_id):
        """Recupera chunks de um documento específico"""
        if self.mock_mode:
            return [chunk for chunk in self.mock_chunks if chunk["document_id"] == document_id]
        
        conn = self.connect()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, chunk_text, chunk_index, metadata FROM document_chunks WHERE document_id = %s ORDER BY chunk_index",
                (document_id,)
            )
            
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            chunks = []
            for result in results:
                chunks.append({
                    "id": result[0],
                    "chunk_text": result[1],
                    "chunk_index": result[2],
                    "metadata": result[3]
                })
            
            return chunks
        except Exception as e:
            print(f"Erro ao recuperar chunks: {e}")
            if conn:
                conn.close()
            return []
    
    def list_documents(self):
        """Lista todos os documentos armazenados"""
        if self.mock_mode:
            return self.mock_documents
        
        conn = self.connect()
        if not conn:
            return []
        
        try:
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, filename, file_type, file_size, upload_date, metadata FROM documents ORDER BY upload_date DESC"
            )
            
            results = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            documents = []
            for result in results:
                documents.append({
                    "id": result[0],
                    "filename": result[1],
                    "file_type": result[2],
                    "file_size": result[3],
                    "upload_date": result[4],
                    "metadata": result[5]
                })
            
            return documents
        except Exception as e:
            print(f"Erro ao listar documentos: {e}")
            if conn:
                conn.close()
            return []
    
    def store_query(self, query_text, document_id, result_text):
    # """Armazena uma consulta e seu resultado"""
        if self.mock_mode:
            document_info = f"para documento {document_id}" if document_id else "global (todos os documentos)"
            print(f"Simulando armazenamento de consulta: '{query_text}' {document_info}")
            return True
        
        conn = self.connect()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            
            # Modificado para aceitar document_id como NULL para consultas globais
            cursor.execute(
                "INSERT INTO queries (query_text, document_id, result_text) VALUES (%s, %s, %s)",
                (query_text, document_id, result_text)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
        except Exception as e:
            print(f"Erro ao armazenar consulta: {e}")
            if conn:
                conn.close()
            return False
    
    def delete_document(self, document_id):
        """Exclui um documento e seus chunks"""
        if self.mock_mode:
            self.mock_documents = [doc for doc in self.mock_documents if doc["id"] != document_id]
            self.mock_chunks = [chunk for chunk in self.mock_chunks if chunk["document_id"] != document_id]
            print(f"Documento simulado {document_id} excluído")
            return True
        
        conn = self.connect()
        if not conn:
            return False
        
        try:
            cursor = conn.cursor()
            
            # A exclusão em cascata dos chunks é tratada pela restrição ON DELETE CASCADE
            cursor.execute("DELETE FROM documents WHERE id = %s", (document_id,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return True
        except Exception as e:
            print(f"Erro ao excluir documento: {e}")
            if conn:
                conn.close()
            return False
