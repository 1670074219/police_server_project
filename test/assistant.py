from ragflow_sdk import RAGFlow

rag_object = RAGFlow(api_key="ragflow-Q4NDg1OWU2MDQ4YTExZjBhYjQwMDI0Mm", base_url="http://192.168.101.206:80")
for assistant in rag_object.list_chats():
    print(assistant)