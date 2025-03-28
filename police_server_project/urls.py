"""
URL configuration for police_server_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from main_conponent.views import home, chat, agent

urlpatterns = [
    # path('admin/', admin.site.urls),
    # main page
    path('home_page', home.home_page, name='home_page'),
    path('api/chat', home.chat_with_model, name='chat_with_model'),
    path('api/set_model', home.set_model, name='set_model'),

    path('chat_page', chat.chat_page, name='chat_page'),

    path('agent_page', agent.agent_page, name='agent_page'),
]
