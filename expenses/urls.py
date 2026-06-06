from django.urls import path

from . import views

app_name = "expenses"

urlpatterns = [
    path("categories/", views.expense_category_list, name="expense_category_list"),
    path("categories/new/", views.expense_category_create, name="expense_category_create"),
    path("categories/quick-create/", views.expense_category_quick_create, name="expense_category_quick_create"),
    path("categories/<int:category_id>/edit/", views.expense_category_edit, name="expense_category_edit"),
    path("categories/<int:category_id>/deactivate/", views.expense_category_deactivate, name="expense_category_deactivate"),
    path("categories/<int:category_id>/delete/", views.expense_category_delete, name="expense_category_delete"),
    path("", views.expense_list, name="expense_list"),
    path("new/", views.expense_create, name="expense_create"),
    path("<uuid:expense_id>/edit/", views.expense_edit, name="expense_edit"),
    path("<uuid:expense_id>/post/", views.post_expense, name="post_expense"),
    path("<uuid:expense_id>/void/", views.void_expense, name="void_expense"),
    path(
        "<uuid:expense_id>/attachments/<uuid:attachment_id>/delete/",
        views.expense_delete_attachment,
        name="expense_delete_attachment",
    ),
]
