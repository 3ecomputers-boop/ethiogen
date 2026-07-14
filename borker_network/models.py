from django.db import models
from django.conf import settings


class Broker(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='broker_profile'
    )
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    network_level = models.PositiveIntegerField(default=0)
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Broker"
        verbose_name_plural = "Brokers"
        ordering = ['-created_at']

    def __str__(self):
        return self.user.get_username()


class Deal(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_CLOSED = 'closed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_CLOSED, 'Closed'),
    ]

    broker = models.ForeignKey(
        Broker,
        on_delete=models.CASCADE,
        related_name='deals'
    )

    client_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission = models.DecimalField(max_digits=12, decimal_places=2)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.client_name} - {self.status.title()}"


class Payout(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_COMPLETED = 'completed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_COMPLETED, 'Completed'),
    ]

    broker = models.ForeignKey(
        Broker,
        on_delete=models.CASCADE,
        related_name='payouts'
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.broker} - {self.amount}"


class Task(models.Model):
    broker = models.ForeignKey(
        Broker,
        on_delete=models.CASCADE,
        related_name='tasks'
    )

    title = models.CharField(max_length=255)
    description = models.TextField()
    deadline = models.DateTimeField()

    completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['completed', 'deadline']

    def __str__(self):
        return self.title