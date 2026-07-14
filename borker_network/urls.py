from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('tasks/', views.task_list, name='task_list'),
    path('tasks/complete/<int:task_id>/', views.complete_task, name='complete_task'),
]