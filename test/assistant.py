from ragflow_sdk import RAGFlow

rag_object = RAGFlow(api_key="ragflow-BhYTBmYWUyMGVmOTExZjBiMDIzNmE4Yj", base_url="http://219.216.99.136:6523")
for assistant in rag_object.list_chats():
    print(assistant)