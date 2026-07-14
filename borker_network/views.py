from django.shortcuts import render
from .models import Broker, Deal, Payout

def dashboard(request):
    broker = Broker.objects.get(user=request.user)
    deals = Deal.objects.filter(broker=broker)
    payouts = Payout.objects.filter(broker=broker)
    context = {
        'broker': broker,
        'deals': deals,
        'payouts': payouts
    }
    return render(request, 'broker_network/dashboard.html', context)
from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from .models import Task


def task_list(request):
    tasks = Task.objects.filter(broker__user=request.user)
    return render(request, 'broker_network/task_list.html', {'tasks': tasks})


def complete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id)
    task.completed = True
    task.save()
    return HttpResponseRedirect('/broker_network/tasks/')
