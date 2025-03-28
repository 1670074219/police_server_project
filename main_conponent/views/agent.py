from django.shortcuts import render

def agent_page(request):
    return render(request, 'agent.html')