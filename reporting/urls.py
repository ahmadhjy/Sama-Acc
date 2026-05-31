from django.contrib.auth.decorators import login_required
from django.urls import path

from . import views

app_name = "reporting"

urlpatterns = [
    path("", login_required(views.reports_home), name="reports_home"),
    path("activity-trial-balance/", login_required(views.activity_trial_balance), name="activity_trial_balance"),
    path("clients-trial-balance/", login_required(views.clients_trial_balance), name="clients_trial_balance"),
    path("suppliers-trial-balance/", login_required(views.suppliers_trial_balance), name="suppliers_trial_balance"),
    path("ar-aging/", login_required(views.ar_aging), name="ar_aging"),
    path("ap-aging/", login_required(views.ap_aging), name="ap_aging"),
    path("cash-movement/", login_required(views.cash_movement), name="cash_movement"),
    path("opex-by-category/", login_required(views.opex_by_category), name="opex_by_category"),
    path("statements/clients/all/", login_required(views.all_clients_statement), name="all_clients_statement"),
    path("statements/suppliers/all/", login_required(views.all_suppliers_statement), name="all_suppliers_statement"),
    path("client-statement/<uuid:client_id>/", login_required(views.client_statement), name="client_statement"),
    path("supplier-statement/<uuid:supplier_id>/", login_required(views.supplier_statement), name="supplier_statement"),
    path("salesman/", login_required(views.salesman_reports_home), name="salesman_reports_home"),
    path("salesman/<uuid:employee_id>/brief/", login_required(views.salesman_brief_report), name="salesman_brief_report"),
    path("salesman/<uuid:employee_id>/detailed/", login_required(views.salesman_detailed_report), name="salesman_detailed_report"),
]
