# NMTG MES ? UI/UX Codebase Audit

Generated: 13-08-2026 12:10 PM

> This is a static code audit of the MES frontend. It identifies structure, consistency, accessibility, forms, placeholders, tables, CSS and interaction patterns. Actual rendered-screen usability should be validated separately.

## 1. Executive Summary

**Heuristic UI foundation score: 0/100**

- Templates inspected: **15**
- CSS files inspected: **13**
- JavaScript files inspected: **16**
- Flask routes discovered: **134**
- Form controls inspected: **96**
- Findings: **164** (High 2, Medium 141, Low 21)

The redesign should treat ERPNext as a reference for **clarity, information hierarchy, compact business forms, list views, filters and navigation consistency**, rather than copying ERPNext visually. NMTG MES should retain its production-focused workflows, process rails, live WIP status and shop-floor speed while adopting a more consistent enterprise UI system.

## 2. UI Surface Inventory

| Template | Controls | Buttons | Tables | Inline styles | Search | Filter | Modal |
| --- | --- | --- | --- | --- | --- | --- | --- |
| templates\admin_dashboard.html | 0 | 2 | 1 | 16 |  |  | Yes |
| templates\base.html | 1 | 4 | 0 | 0 |  | Yes | Yes |
| templates\bom_summary.html | 1 | 9 | 1 | 0 | Yes | Yes |  |
| templates\dispatch_tracker.html | 6 | 9 | 0 | 3 | Yes | Yes | Yes |
| templates\jc_review.html | 1 | 8 | 3 | 10 | Yes | Yes | Yes |
| templates\login.html | 2 | 1 | 0 | 2 |  |  |  |
| templates\oee.html | 6 | 3 | 1 | 0 | Yes | Yes |  |
| templates\operator_dashboard.html | 0 | 1 | 0 | 2 |  |  |  |
| templates\page1.html | 21 | 13 | 3 | 40 | Yes | Yes | Yes |
| templates\page2.html | 22 | 17 | 1 | 26 | Yes | Yes | Yes |
| templates\page3.html | 8 | 12 | 0 | 65 | Yes |  | Yes |
| templates\page4.html | 0 | 0 | 0 | 26 |  |  |  |
| templates\page5.html | 24 | 18 | 2 | 97 | Yes | Yes | Yes |
| templates\supervisor_dashboard.html | 0 | 1 | 0 | 5 |  |  |  |
| templates\user_management.html | 4 | 15 | 1 | 0 |  |  | Yes |

## 3. Flask Route ? UI Template Map

| Route | Methods | Function | Template | Backend file |
| --- | --- | --- | --- | --- |
| /api/analytics/summary | GET | analytics_summary |  | routes\analytics.py |
| /api/analytics/wip_flow | GET | analytics_wip_flow |  | routes\analytics.py |
| /api/analytics/daily_activity | GET | analytics_daily_activity |  | routes\analytics.py |
| /api/analytics/process_delays | GET | analytics_process_delays |  | routes\analytics.py |
| /api/analytics/overdue_jobs | GET | analytics_overdue_jobs |  | routes\analytics.py |
| /api/analytics/supervisor_stages | GET | analytics_supervisor_stages |  | routes\analytics.py |
| /api/analytics/otd | GET | analytics_otd |  | routes\analytics.py |
| /api/analytics/wip_distribution | GET | wip_distribution |  | routes\analytics.py |
| /api/analytics/quality_by_item | GET | analytics_quality_by_item |  | routes\analytics.py |
| /api/analytics/supervisor_performance | GET | analytics_supervisor_performance |  | routes\analytics.py |
| /api/analytics/daily_checks | GET | analytics_daily_checks |  | routes\analytics.py |
| /api/analytics/daily_breakdown | GET | analytics_daily_breakdown |  | routes\analytics.py |
| /api/audit_trail | GET | get_audit_trail |  | routes\audit_trail.py |
| /api/audit_trail/<path:job_card_no> | GET | get_audit_trail_by_jc |  | routes\audit_trail.py |
| /login | GET, POST | login | login.html | routes\auth.py |
| /logout | GET | logout |  | routes\auth.py |
| /api/bom/summary | GET | get_bom_summary |  | routes\bom.py |
| /api/bom/children/<parent_code> | GET | get_children |  | routes\bom.py |
| /api/bom/item_details/<child_code> | GET | get_item_details |  | routes\bom.py |
| /api/cutting-plan/health | GET | health |  | routes\cutting_plan.py |
| /api/cutting-plan/manual | POST | create_manual |  | routes\cutting_plan.py |
| /api/cutting-plan/auto-test | POST | auto_test |  | routes\cutting_plan.py |
| /api/cutting-plan/plans | GET | list_plans |  | routes\cutting_plan.py |
| /api/cutting-plan/<int:plan_id> | PATCH, PUT | edit_cutting_plan |  | routes\cutting_plan.py |
| /api/cutting-plan/<int:plan_id>/release | POST | release_plan |  | routes\cutting_plan.py |
| /api/cutting-plan/<int:plan_id>/cancel | POST | cancel_cutting_plan |  | routes\cutting_plan.py |
| /api/cutting-plan/<int:plan_id>/batches | POST | add_batch |  | routes\cutting_plan.py |
| /api/cutting-plan/<int:plan_id>/batches/<int:batch_id>/undo | POST | undo_cutting_batch |  | routes\cutting_plan.py |
| /api/data/job_cards/filter_options | GET | data_job_card_filter_options |  | routes\data_view.py |
| /api/data/job_cards | GET | data_job_cards |  | routes\data_view.py |
| /api/job_card_item/priority | POST | update_item_priority |  | routes\data_view.py |
| /api/job_card_item/soft_delete | POST | soft_delete_job_card_item |  | routes\data_view.py |
| /api/data/quality_checks | GET | data_quality_checks |  | routes\data_view.py |
| /api/audit_trail | GET | get_audit_trail |  | routes\data_view.py |
| /api/audit_trail/<path:job_card_no> | GET | get_audit_trail_by_jc |  | routes\data_view.py |
| /api/data/process_report | GET | data_process_report |  | routes\data_view.py |
| /api/data/planning_sheet | GET | data_planning_sheet |  | routes\data_view.py |
| /api/operator/lead-time-notifications | GET | operator_lead_time_notifications |  | routes\data_view.py |
| /api/supervisor/dashboard-summary | GET | supervisor_dashboard_summary |  | routes\data_view.py |
| /api/admin/dashboard-summary | GET | admin_dashboard_summary |  | routes\data_view.py |
| /api/dashboard/stat-detail | GET | stat_detail |  | routes\data_view.py |
| /api/job_card/update_fields | POST | update_job_card_fields |  | routes\data_view.py |
| /api/wip_summary | GET | get_wip_summary |  | routes\data_view.py |
| /api/wip_summary/detail | GET | get_wip_summary_detail |  | routes\data_view.py |
| /api/notifications/delivery_changes | GET | get_delivery_change_notifications |  | routes\data_view.py |
| /api/dispatch/tracker | GET | dispatch_tracker |  | routes\data_view.py |
| /api/dispatch/update_wo_dd | POST | dispatch_update_wo_dd |  | routes\data_view.py |
| /api/dispatch/update_so_dd | POST | dispatch_update_so_dd |  | routes\data_view.py |
| /api/data/assembly_readiness | GET | assembly_readiness |  | routes\data_view.py |
| /api/dispatch-tracker/export-excel | GET | dispatch_tracker_export_excel |  | routes\data_view.py |
| /api/job_card/review/compare | POST | review_compare_process_route |  | routes\job_cards.py |
| /api/job_card/review/update/<int:review_id> | POST | update_upload_review_processes |  | routes\job_cards.py |
| /api/job_card/review/create_process_master/<int:review_id> | POST | create_review_item_in_process_master |  | routes\job_cards.py |
| /api/job_card/review/update_process_master/<int:review_id> | POST | update_process_master_from_review |  | routes\job_cards.py |
| /api/job_card/review/recheck/<int:review_id> | POST | recheck_upload_review |  | routes\job_cards.py |
| /api/job_card/review/batch/<review_token> | GET | get_upload_review_batch |  | routes\job_cards.py |
| /api/job_card/review/item/<item_code> | GET | review_item_process_route |  | routes\job_cards.py |
| /api/items | GET | get_items |  | routes\job_cards.py |
| /api/customer-search | GET | customer_search |  | routes\job_cards.py |
| /api/process_names | GET | get_process_names |  | routes\job_cards.py |
| /api/supervisors | GET | get_supervisors |  | routes\job_cards.py |
| /api/job_card | POST | save_job_card |  | routes\job_cards.py |
| /api/job_card/bulk_create | POST | bulk_create_job_cards |  | routes\job_cards.py |
| /api/job_cards | GET | get_job_cards |  | routes\job_cards.py |
| /api/process_default_days | GET | get_process_default_days |  | routes\job_cards.py |
| /api/job_card/upload_preview | POST | upload_preview_job_cards |  | routes\job_cards.py |
| /api/job_card/upload_confirm | POST | upload_confirm_job_cards |  | routes\job_cards.py |
| /api/so_mapping/status | GET | get_so_mapping_status |  | routes\job_cards.py |
| /api/advance-plan/customer-search | GET | advance_plan_customer_search |  | routes\job_cards.py |
| /api/advance-plan/allocations/<int:item_id> | GET | advance_plan_get_allocations |  | routes\job_cards.py |
| /api/advance-plan/allocations | POST | advance_plan_create_allocation |  | routes\job_cards.py |
| /api/advance-plan/allocations/<int:allocation_id> | PUT | advance_plan_update_allocation |  | routes\job_cards.py |
| /api/advance-plan/allocations/<int:allocation_id>/cancel | POST | advance_plan_cancel_allocation |  | routes\job_cards.py |
| /api/oee/master-data | GET | oee_master_data |  | routes\oee.py |
| /api/oee/context/<path:job_card_no> | GET | oee_job_context |  | routes\oee.py |
| /api/oee/results | GET | oee_results |  | routes\oee.py |
| / | GET | index | page1.html | routes\pages.py |
| /page2 | GET | page2 | page2.html | routes\pages.py |
| /page3 | GET | page3 | page3.html | routes\pages.py |
| /oee | GET | oee_page | oee.html | routes\pages.py |
| /page4 | GET | page4 | page4.html | routes\pages.py |
| /page5 | GET | page5 | page5.html | routes\pages.py |
| /smart-upload | GET | smart_upload | smart_upload.html | routes\pages.py |
| /user-management | GET | user_management | user_management.html | routes\pages.py |
| /dispatch-tracker | GET | dispatch_tracker | dispatch_tracker.html | routes\pages.py |
| /jc_review | GET | jc_review | jc_review.html | routes\pages.py |
| /api/bom/roots | GET | get_roots |  | routes\process_master.py |
| /api/bom/tree/children/<item_code> | GET | get_children |  | routes\process_master.py |
| /api/bom/search | GET | search_items |  | routes\process_master.py |
| /api/bom/item/<item_code> | GET | get_item |  | routes\process_master.py |
| /api/bom/item | POST | add_item |  | routes\process_master.py |
| /api/bom/item/<item_code> | PUT | update_item |  | routes\process_master.py |
| /api/bom/item/<item_code>/changes | GET | get_item_changes |  | routes\process_master.py |
| /api/bom/item/<item_code> | DELETE | delete_item |  | routes\process_master.py |
| /api/bom/processes | GET | get_processes |  | routes\process_master.py |
| /api/bom/link | POST | add_bom_link |  | routes\process_master.py |
| /api/bom/link/<int:link_id> | PUT | update_bom_link |  | routes\process_master.py |
| /api/bom/link/<int:link_id> | DELETE | delete_bom_link |  | routes\process_master.py |
| /api/bom/upload_preview | POST | upload_preview |  | routes\process_master.py |
| /api/bom/upload_confirm | POST | upload_confirm |  | routes\process_master.py |
| /api/bom/stats | GET | get_stats |  | routes\process_master.py |
| /api/bom/bom_tree | GET | get_bom_tree |  | routes\process_master.py |
| /api/bom/bom_tree_nested | GET | get_bom_tree_nested |  | routes\process_master.py |
| /api/bom/process_flow/<bom_no> | GET | get_bom_process_flow |  | routes\process_master.py |
| /api/quality_check/fetch/<path:job_card_no> | GET | fetch_for_quality_check |  | routes\quality_check.py |
| /api/quality_check/child_c_gate/continue_anyway | POST | continue_anyway_child_c_gate |  | routes\quality_check.py |
| /api/wip/update | POST | update_wip |  | routes\quality_check.py |
| /api/operator/recent_completions | GET | operator_recent_completions |  | routes\quality_check.py |
| /api/operator/undo_completion | POST | operator_undo_completion |  | routes\quality_check.py |
| /api/quality_check | POST | save_quality_check |  | routes\quality_check.py |
| /api/quality_check/history/<path:job_card_no> | GET | get_quality_history |  | routes\quality_check.py |
| /api/wip/subcontract | POST | set_subcontract |  | routes\quality_check.py |
| /api/wip/subcontract_complete | POST | complete_subcontract |  | routes\quality_check.py |
| /api/wip/rollback | POST | rollback_wip_stage |  | routes\quality_check.py |
| /api/revoke/list/<path:job_card_no> | GET | get_revoke_list |  | routes\quality_check.py |
| /api/revoke/advance-rework | POST | advance_rework_stage |  | routes\quality_check.py |
| /api/revoke/merge | POST | merge_revoke |  | routes\quality_check.py |
| /api/wip/remove_process | POST | remove_process |  | routes\quality_check.py |
| /api/dashboard/overdue-c-parent-status | GET | overdue_c_parent_status_api |  | routes\quality_check.py |
| /api/wip/check-c-child-gate/<job_card_no> | GET | check_c_child_gate_api |  | routes\quality_check.py |
| /api/operator/job_cards | GET | operator_job_cards |  | routes\quality_check.py |
| /api/smart_upload/detect | POST | detect_format |  | routes\smart_upload.py |
| /api/smart_upload/save_mapping | POST | save_mapping |  | routes\smart_upload.py |
| /api/smart_upload/parse | POST | parse_with_mapping |  | routes\smart_upload.py |
| /api/users/create | POST | create_user |  | routes\users.py |
| /api/users | GET | list_users |  | routes\users.py |
| /api/user-management/users | GET | user_management_users |  | routes\users.py |
| /api/user-management/permission-master | GET | permission_master |  | routes\users.py |
| /api/user-management/permissions/<int:user_id> | GET | get_user_permissions |  | routes\users.py |
| /api/user-management/save-permissions | POST | save_user_permissions |  | routes\users.py |
| /api/users/<int:user_id>/toggle-active | POST | toggle_user_active |  | routes\users.py |
| /api/users/<int:user_id>/update-role | POST | update_user_role |  | routes\users.py |
| /api/permissions/meta | GET | get_permissions_meta |  | routes\users.py |
| /api/users/<int:user_id>/permissions | GET, POST | user_permissions |  | routes\users.py |

## 4. Forms, Fields & Placeholder Audit

- Total controls: **96**
- Controls using placeholders: **39**
- Potentially unlabeled controls: **75**

### Most-used placeholders

| Placeholder | Occurrences |
| --- | --- |
| Enter remark for this stage change... | 2 |
| Enter vendor / subcontractor name | 2 |
| e.g. 5 | 2 |
| Search parent code, child code or item description | 1 |
| Search customer, SO, WO or job card… | 1 |
| Enter reason… | 1 |
| Enter SO No. | 1 |
| Search customer code or name... | 1 |
| Qty | 1 |
| Search job card, BOM, parent, child, item... | 1 |
| Search JC / Item / Machine... | 1 |
| 42219 | 1 |
| 1001 | 1 |
| Enter customer name | 1 |
| Optional remarks | 1 |
| Enter parent code | 1 |
| Filter child codes... | 1 |
| Enter child code | 1 |
| e.g. 108553 | 1 |
| Type to search item... | 1 |
| Enter qty | 1 |
| Enter advance stock | 1 |
| Search BOM No, item code, description... | 1 |
| e.g. NAINR0001234 | 1 |
| e.g. Inner Race of NHB 40 | 1 |
| e.g. 42x125x35 | 1 |
| e.g. EN9 | 1 |
| e.g. Inner Race | 1 |
| Enter why this item or process routing is being changed | 1 |
| e.g. 108553 or 108554/108701 | 1 |
| Enter reason for allowing this Job Card to continue... | 1 |
| Search job cards... | 1 |
| Enter reason for changing delivery date... | 1 |
| e.g. jdoe | 1 |
| Minimum 6 characters | 1 |
| e.g. John Doe | 1 |

### Recommended MES form pattern

- Persistent field label above the control.
- Placeholder only for examples such as `e.g. 0000112738`.
- Required state shown consistently.
- Help/error message directly below the field.
- Searchable master-data fields visually differentiated from free-text fields.
- Read-only system values styled differently from user-entered values.

## 5. Visual Design-System Audit

- Unique color values: **261**
- Unique font-size declarations: **37**
- Font-family declarations: **8**
- Border-radius variants: **28**
- CSS custom variables discovered: **63**
- `!important` declarations: **580**
- Responsive media queries: **48**

### Most-used colors

| Color | Uses |
| --- | --- |
| #ffffff | 173 |
| #dc2626 | 42 |
| #16a34a | 36 |
| #1e3a5f | 35 |
| #eff6ff | 33 |
| #d7dde6 | 32 |
| #1a56db | 32 |
| #64748b | 29 |
| #fef2f2 | 29 |
| #fca5a5 | 27 |
| #92400e | 26 |
| #2563eb | 21 |
| #fffbeb | 21 |
| #bfdbfe | 20 |
| #f8fafc | 20 |
| #bbf7d0 | 19 |
| #fff | 19 |
| rgba(0, 0, 0, 0.07) | 18 |
| #f59e0b | 17 |
| #f0fdf4 | 16 |
| #fde68a | 15 |
| #0f172a | 14 |
| #86efac | 14 |
| #0f2a4d | 14 |
| #cbd5e1 | 14 |

### Font sizes

| Font size | Uses |
| --- | --- |
| 13px | 96 |
| 12px | 83 |
| 11px | 82 |
| 14px | 63 |
| 10px | 29 |
| 18px | 17 |
| 16px | 14 |
| 15px | 14 |
| 12px !important | 11 |
| 24px | 10 |
| 28px | 8 |
| 13px !important | 8 |
| 20px | 7 |
| 40px | 6 |
| 26px | 5 |
| 15px !important | 5 |
| 13.5px | 5 |
| 34px | 4 |
| 22px | 4 |
| 17px | 4 |
| 36px | 3 |
| 11.5px | 3 |
| 12.5px | 3 |
| 19px | 2 |
| 21px | 2 |

### CSS variables

| Variable | Uses |
| --- | --- |
| --bg | 6 |
| --surface | 6 |
| --surface2 | 6 |
| --border | 6 |
| --accent | 6 |
| --text | 6 |
| --muted | 6 |
| --danger | 6 |
| --success | 6 |
| --header-bg | 6 |
| --header-text | 5 |
| --accent2 | 2 |
| --accent-soft | 2 |
| --radius-sm | 2 |
| --sidebar-width | 1 |
| --review-bg | 1 |
| --review-surface | 1 |
| --review-surface-2 | 1 |
| --review-border | 1 |
| --review-border-strong | 1 |
| --review-text | 1 |
| --review-muted | 1 |
| --review-blue | 1 |
| --review-blue-soft | 1 |
| --review-green | 1 |
| --review-green-soft | 1 |
| --review-teal | 1 |
| --review-teal-soft | 1 |
| --review-red | 1 |
| --review-red-soft | 1 |
| --review-orange | 1 |
| --review-orange-soft | 1 |
| --review-purple | 1 |
| --review-purple-soft | 1 |
| --review-gray-soft | 1 |
| --review-shadow | 1 |
| --review-radius | 1 |
| --review-radius-lg | 1 |
| --review-mono | 1 |
| --danger-soft | 1 |

## 6. Button & Action Language

| Button label | Occurrences |
| --- | --- |
| Cancel | 17 |
| ✕ | 4 |
| × | 3 |
| Confirm | 3 |
| Filters | 2 |
| Clear | 2 |
| Apply | 2 |
| Upload Different File | 2 |
| Confirm Import | 2 |
| Testing | 2 |
| Shortage | 2 |
| Yes, Roll Back The Stage | 2 |
| ☰ | 1 |
| Get Started | 1 |
| Make (A) | 1 |
| Buy (I) | 1 |
| Has Processes | 1 |
| No Processes | 1 |
| Clear Filters | 1 |
| Export to Excel | 1 |
| Prev | 1 |
| Next | 1 |
| Overdue only | 1 |
| Due this week | 1 |
| Expand all | 1 |
| Save Change | 1 |
| Cancel Edit | 1 |
| Assign Quantity | 1 |
| Import Ready | 1 |
| Retry | 1 |
| Clear filters | 1 |
| Previously Approved These routes were approved earlier and do not require another manual review. 0 | 1 |
| Import now | 1 |
| Login | 1 |
| Select All | 1 |
| Deselect All | 1 |
| Most Urgent | 1 |
| Reset | 1 |
| Upload Excel | 1 |
| Save Job Card | 1 |
| Back to Edit | 1 |
| Confirm & Create | 1 |
| Select Files | 1 |
| Load more | 1 |
| Save Item | 1 |
| Add Process | 1 |
| Save Changes | 1 |
| Delete | 1 |
| Select File | 1 |
| Fetch Records | 1 |
| Submit | 1 |
| Continue Anyway | 1 |
| Remove | 1 |
| PPC | 1 |
| WIP Summary | 1 |
| Clear All Filters | 1 |
| Columns | 1 |
| Excel | 1 |
| PDF | 1 |
| Confirm & Save | 1 |

The redesign should standardize action hierarchy:

- **Primary:** Save, Submit, Complete, Assign.
- **Secondary:** Edit, Refresh, Export, View.
- **Tertiary:** filters, expand/collapse, utility controls.
- **Danger:** Delete, Cancel allocation, Reject.
- Avoid making every action visually equal.

## 7. Tables, Lists & Operational Views

Tables detected: **13**

For MES list-heavy screens, the recommended standard is:

- Sticky page toolbar.
- Search + structured filters in one consistent area.
- Saved/default filters where useful.
- Sticky table header.
- Clear row hover and selected state.
- Status badges instead of raw status text.
- Right-aligned numeric quantities.
- Standard date formatting.
- Column visibility control on high-density pages.
- Export action in the same toolbar position across modules.
- Empty-state message with a clear next action.

## 8. Navigation & Information Architecture

ERPNext is useful here as a reference for enterprise hierarchy, but the MES should use an NMTG-specific navigation model.

Recommended shell:

1. Persistent collapsible left sidebar.
2. Page title + breadcrumb in a common top area.
3. Page-level actions on the right.
4. Search/filter toolbar below the title.
5. Main content area using standardized cards/list views.
6. User/role controls separated from operational actions.

Suggested MES navigation groups:

- **Production** ? PPC, Job Cards, Process movement.
- **Quality** ? Quality Check, inspection, traceability.
- **Planning** ? Advance Plan, Dispatch Tracker.
- **Performance** ? Analytics, OEE.
- **Masters** ? Process Master, customer/item masters.
- **Administration** ? Users, rights, audit trail.

## 9. ERPNext-Inspired Direction ? Without Copying ERPNext

Use ERPNext mainly as a reference for:

- Consistent sidebar and page hierarchy.
- Compact enterprise typography.
- Clean list views.
- Standard filter controls.
- Unified form field behavior.
- Predictable primary/secondary actions.
- Status pills and document-state visibility.
- Clear separation between list, form and dashboard views.

Do **not** copy ERPNext blindly. NMTG MES requires:

- More visible WIP/process state.
- Faster shop-floor actions.
- Larger critical quantities/statuses.
- Strong overdue/priority indicators.
- Production-friendly process rails.
- Minimal clicks for operators.
- Role-specific information density.

## 10. Recommended NMTG MES UI Component System

Create shared components/styles for:

- `mes-page-header`
- `mes-breadcrumb`
- `mes-toolbar`
- `mes-search`
- `mes-filter-chip`
- `mes-card`
- `mes-kpi-card`
- `mes-table`
- `mes-status-badge`
- `mes-form-group`
- `mes-modal`
- `mes-drawer`
- `mes-empty-state`
- `mes-toast`
- `mes-process-rail`
- `mes-action-menu`

## 11. Recommended Design Tokens

Before redesigning individual pages, define global tokens for:

- Brand / primary color.
- Background and surface colors.
- Main, secondary and muted text.
- Border/divider colors.
- Success, warning, danger and information.
- 4/8px-based spacing scale.
- Compact enterprise typography scale.
- 3 standard border-radius sizes.
- 2?3 elevation/shadow levels.
- Sidebar width.
- Toolbar height.
- Form control height.
- Table row density.

## 12. Role-Specific UX Direction

The same MES shell can be used for all roles, but information density should vary.

### Operator
- Current JC and current process first.
- Large Start/Complete/Qty actions.
- Minimal navigation and low cognitive load.

### Supervisor
- WIP overview.
- Exceptions, delays, blocked JCs and quality status.
- Faster drill-down into process history.

### Admin / Management
- Full navigation.
- Analytics, configuration and audit controls.
- Dense lists acceptable, with filtering and export.

## 13. Detailed Findings

| Severity | Category | Location | Finding | Recommendation |
| --- | --- | --- | --- | --- |
| HIGH | Design System | GLOBAL | 261 distinct CSS color values are used across the UI. | Create one global MES color-token system before page-by-page redesign. |
| HIGH | Forms | GLOBAL | 75 form controls may rely on placeholder/context instead of a persistent label. | Adopt a common field component: label + control + optional hint/error. Do not use placeholders as field names. |
| MEDIUM | Buttons & Accessibility | templates\admin_dashboard.html:189 | Button has no visible or accessible name. | Add visible text, aria-label or title so the action is understandable. |
| MEDIUM | Buttons & Accessibility | templates\page1.html:590 | Button has no visible or accessible name. | Add visible text, aria-label or title so the action is understandable. |
| MEDIUM | Buttons & Accessibility | templates\page5.html:110 | Button has no visible or accessible name. | Add visible text, aria-label or title so the action is understandable. |
| MEDIUM | Buttons & Accessibility | templates\user_management.html:43 | Button has no visible or accessible name. | Add visible text, aria-label or title so the action is understandable. |
| MEDIUM | Buttons & Accessibility | templates\user_management.html:102 | Button has no visible or accessible name. | Add visible text, aria-label or title so the action is understandable. |
| MEDIUM | Buttons & Accessibility | templates\user_management.html:190 | Button has no visible or accessible name. | Add visible text, aria-label or title so the action is understandable. |
| MEDIUM | CSS Maintainability | static\css\page2.css:1 | 386 !important declarations found. | Reduce specificity conflicts before redesigning; establish reusable component classes and tokens. |
| MEDIUM | CSS Maintainability | static\css\page3.css:1 | 14 !important declarations found. | Reduce specificity conflicts before redesigning; establish reusable component classes and tokens. |
| MEDIUM | CSS Maintainability | static\css\page5.css:1 | 85 !important declarations found. | Reduce specificity conflicts before redesigning; establish reusable component classes and tokens. |
| MEDIUM | CSS Maintainability | static\css\responsive.css:1 | 78 !important declarations found. | Reduce specificity conflicts before redesigning; establish reusable component classes and tokens. |
| MEDIUM | Design Consistency | templates\admin_dashboard.html:1 | 16 inline style attributes found. | Move repeated visual rules into shared CSS classes/design tokens to simplify the redesign. |
| MEDIUM | Design Consistency | templates\jc_review.html:1 | 10 inline style attributes found. | Move repeated visual rules into shared CSS classes/design tokens to simplify the redesign. |
| MEDIUM | Design Consistency | templates\page1.html:1 | 40 inline style attributes found. | Move repeated visual rules into shared CSS classes/design tokens to simplify the redesign. |
| MEDIUM | Design Consistency | templates\page2.html:1 | 26 inline style attributes found. | Move repeated visual rules into shared CSS classes/design tokens to simplify the redesign. |
| MEDIUM | Design Consistency | templates\page3.html:1 | 65 inline style attributes found. | Move repeated visual rules into shared CSS classes/design tokens to simplify the redesign. |
| MEDIUM | Design Consistency | templates\page4.html:1 | 26 inline style attributes found. | Move repeated visual rules into shared CSS classes/design tokens to simplify the redesign. |
| MEDIUM | Design Consistency | templates\page5.html:1 | 97 inline style attributes found. | Move repeated visual rules into shared CSS classes/design tokens to simplify the redesign. |
| MEDIUM | Design Consistency | templates\supervisor_dashboard.html:1 | 5 inline style attributes found. | Move repeated visual rules into shared CSS classes/design tokens to simplify the redesign. |
| MEDIUM | Forms & Accessibility | templates\bom_summary.html:372 | input control #bom-search has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\dispatch_tracker.html:1670 | input control #dt-search has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\dispatch_tracker.html:1695 | input control #dt-dd-new-date has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\dispatch_tracker.html:1698 | textarea control #dt-dd-reason has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\jc_review.html:65 | input control #search-input has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\oee.html:883 | input control #oee-search has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:235 | input control #so_no has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:247 | input control #work_order_no has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:261 | input control #customer_name has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:281 | input control #delivery_date has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:287 | input control #so_date has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:291 | input control #job_card_date has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:297 | input control #work_order_date has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:301 | input control #remarks has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:315 | input control #parent_code has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:327 | input control #child-search has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:347 | input control #select-all-cb has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:374 | input control #child_code_manual has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:393 | input control #job_card_no has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:401 | input control #item_name has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:417 | input control #item_qty has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:421 | input control #advance_stock has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:466 | input control #is_priority has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:474 | input control #af_material has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:478 | input control #af_size has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:482 | input control #af_part_name has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page1.html:598 | input control #upload-file-input has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1394 | input control #pm-search has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1529 | input control #add-item-code has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1533 | input control #add-item-desc has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1548 | input control #add-item-size has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1552 | input control #add-item-material has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1556 | input control #add-item-part has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1593 | input control #edit-item-code has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1597 | input control #edit-item-desc has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1617 | input control #edit-item-material has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1621 | input control #edit-item-size has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1625 | input control #edit-item-part has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1647 | textarea control #edit-change-remark has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page2.html:1745 | input control #upload-file-input has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page3.html:21 | input control #jc-input has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page3.html:105 | input control #modal-planned-qty has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page3.html:115 | input control #modal-actual-qty has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page3.html:225 | textarea control #modal-stage-remark has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page3.html:269 | input control #subcontract-checkbox has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page3.html:292 | input control #modal-vendor-name has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page3.html:333 | input control #modal-lead-days has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page3.html:546 | textarea control #child-c-gate-override-reason has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:104 | input control #global-search has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:177 | input control #ws-from-date has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:200 | input control #ws-to-date has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:305 | textarea control #dd-reason-input has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:356 | input control #modal-planned-qty has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:360 | input control #modal-actual-qty has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:398 | textarea control #modal-stage-remark has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:402 | input control #subcontract-checkbox has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:410 | input control #modal-vendor-name has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:417 | input control #modal-lead-days has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:464 | input control #ejc-job-card-no has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:468 | input control #ejc-so-no has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:472 | input control #ejc-customer-name has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:476 | input control #ejc-parent-code has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:480 | input control #ejc-child-code has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:484 | input control #ejc-work-order-no has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:488 | input control #ejc-item-name has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:492 | input control #ejc-material has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:497 | input control #ejc-so-qty has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:501 | input control #ejc-actual-qty has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:506 | input control #ejc-delivery-date has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:510 | textarea control #ejc-remarks has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:514 | input control #ejc-is-subcontract has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\page5.html:520 | input control #ejc-vendor-name has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\user_management.html:52 | input control #u-username has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\user_management.html:61 | input control #u-password has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Forms & Accessibility | templates\user_management.html:70 | input control #u-full-name has no explicit label, aria-label or title. | Add a persistent field label. Placeholder text should be supporting guidance, not the only field identity. |
| MEDIUM | Placeholder UX | templates\bom_summary.html:372 | Placeholder-only field: 'Search parent code, child code or item description'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\dispatch_tracker.html:1670 | Placeholder-only field: 'Search customer, SO, WO or job card…'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\dispatch_tracker.html:1698 | Placeholder-only field: 'Enter reason…'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\jc_review.html:65 | Placeholder-only field: 'Search job card, BOM, parent, child, item...'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\oee.html:883 | Placeholder-only field: 'Search JC / Item / Machine...'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page1.html:235 | Placeholder-only field: '42219'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page1.html:247 | Placeholder-only field: '1001'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page1.html:261 | Placeholder-only field: 'Enter customer name'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page1.html:301 | Placeholder-only field: 'Optional remarks'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page1.html:315 | Placeholder-only field: 'Enter parent code'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page1.html:327 | Placeholder-only field: 'Filter child codes...'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page1.html:374 | Placeholder-only field: 'Enter child code'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page1.html:393 | Placeholder-only field: 'e.g. 108553'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page1.html:401 | Placeholder-only field: 'Type to search item...'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page1.html:417 | Placeholder-only field: 'Enter qty'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page1.html:421 | Placeholder-only field: 'Enter advance stock'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page2.html:1394 | Placeholder-only field: 'Search BOM No, item code, description...'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page2.html:1529 | Placeholder-only field: 'e.g. NAINR0001234'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page2.html:1533 | Placeholder-only field: 'e.g. Inner Race of NHB 40'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page2.html:1548 | Placeholder-only field: 'e.g. 42x125x35'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page2.html:1552 | Placeholder-only field: 'e.g. EN9'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page2.html:1556 | Placeholder-only field: 'e.g. Inner Race'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page2.html:1647 | Placeholder-only field: 'Enter why this item or process routing is being changed'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page3.html:21 | Placeholder-only field: 'e.g. 108553 or 108554/108701'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page3.html:225 | Placeholder-only field: 'Enter remark for this stage change...'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page3.html:292 | Placeholder-only field: 'Enter vendor / subcontractor name'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page3.html:333 | Placeholder-only field: 'e.g. 5'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page3.html:546 | Placeholder-only field: 'Enter reason for allowing this Job Card to continue...'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page5.html:104 | Placeholder-only field: 'Search job cards...'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page5.html:305 | Placeholder-only field: 'Enter reason for changing delivery date...'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page5.html:398 | Placeholder-only field: 'Enter remark for this stage change...'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page5.html:410 | Placeholder-only field: 'Enter vendor / subcontractor name'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\page5.html:417 | Placeholder-only field: 'e.g. 5'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\user_management.html:52 | Placeholder-only field: 'e.g. jdoe'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\user_management.html:61 | Placeholder-only field: 'Minimum 6 characters'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Placeholder UX | templates\user_management.html:70 | Placeholder-only field: 'e.g. John Doe'. | Use a visible label above/alongside the field and keep placeholder only as an example or hint. |
| MEDIUM | Typography | GLOBAL | 37 distinct font-size declarations found. | Reduce to a controlled typography scale for page title, section title, body, table, caption and KPI values. |
| MEDIUM | Visual Consistency | static\css\admin_dashboard.css:1 | 37 distinct color values found. | Consolidate colors into semantic design tokens such as primary, surface, border, text, success, warning and danger. |
| MEDIUM | Visual Consistency | static\css\base.css:1 | 53 distinct color values found. | Consolidate colors into semantic design tokens such as primary, surface, border, text, success, warning and danger. |
| MEDIUM | Visual Consistency | static\css\jc_review.css:1 | 66 distinct color values found. | Consolidate colors into semantic design tokens such as primary, surface, border, text, success, warning and danger. |
| MEDIUM | Visual Consistency | static\css\operator_dashboard.css:1 | 31 distinct color values found. | Consolidate colors into semantic design tokens such as primary, surface, border, text, success, warning and danger. |
| MEDIUM | Visual Consistency | static\css\page1.css:1 | 38 distinct color values found. | Consolidate colors into semantic design tokens such as primary, surface, border, text, success, warning and danger. |
| MEDIUM | Visual Consistency | static\css\page2.css:1 | 85 distinct color values found. | Consolidate colors into semantic design tokens such as primary, surface, border, text, success, warning and danger. |
| MEDIUM | Visual Consistency | static\css\page3.css:1 | 65 distinct color values found. | Consolidate colors into semantic design tokens such as primary, surface, border, text, success, warning and danger. |
| MEDIUM | Visual Consistency | static\css\page4.css:1 | 20 distinct color values found. | Consolidate colors into semantic design tokens such as primary, surface, border, text, success, warning and danger. |
| MEDIUM | Visual Consistency | static\css\page5.css:1 | 63 distinct color values found. | Consolidate colors into semantic design tokens such as primary, surface, border, text, success, warning and danger. |
| MEDIUM | Visual Consistency | static\css\supervisor_dashboard.css:1 | 37 distinct color values found. | Consolidate colors into semantic design tokens such as primary, surface, border, text, success, warning and danger. |
| MEDIUM | Visual Consistency | static\css\user_management.css:1 | 54 distinct color values found. | Consolidate colors into semantic design tokens such as primary, surface, border, text, success, warning and danger. |
| LOW | Design System | GLOBAL | 28 different border-radius values found. | Standardize radius tokens for controls, cards, dialogs and badges. |
| LOW | Frontend Maintainability | static\js\page3.js:1 | 47 innerHTML assignments detected. | During redesign, consolidate repeated HTML construction into reusable render/component helpers. |
| LOW | Frontend Maintainability | static\js\page5.js:1 | 37 innerHTML assignments detected. | During redesign, consolidate repeated HTML construction into reusable render/component helpers. |
| LOW | Interaction UX | static\js\hidden_backup.js:1 | 3 alert, 0 confirm and 0 prompt calls detected. | Replace browser-native dialogs with one consistent MES confirmation/dialog component. |
| LOW | Interaction UX | static\js\page2.js:1 | 5 alert, 0 confirm and 0 prompt calls detected. | Replace browser-native dialogs with one consistent MES confirmation/dialog component. |
| LOW | Interaction UX | static\js\page3.js:1 | 4 alert, 1 confirm and 0 prompt calls detected. | Replace browser-native dialogs with one consistent MES confirmation/dialog component. |
| LOW | Interaction UX | static\js\page5.js:1 | 0 alert, 3 confirm and 0 prompt calls detected. | Replace browser-native dialogs with one consistent MES confirmation/dialog component. |
| LOW | Layering | static\css\page1.css:1 | Very high z-index detected (99999). | Create a standard z-index scale for dropdowns, sticky bars, dialogs and toasts. |
| LOW | Layering | static\css\page2.css:1 | Very high z-index detected (99999). | Create a standard z-index scale for dropdowns, sticky bars, dialogs and toasts. |
| LOW | Responsive UX | static\css\admin_dashboard.css:1 | 4 hard-coded widths of 100px+ detected. | Review fixed widths during redesign; prefer grid/flex/minmax where the screen must adapt. |
| LOW | Responsive UX | static\css\base.css:1 | 10 hard-coded widths of 100px+ detected. | Review fixed widths during redesign; prefer grid/flex/minmax where the screen must adapt. |
| LOW | Responsive UX | static\css\jc_review.css:1 | 12 hard-coded widths of 100px+ detected. | Review fixed widths during redesign; prefer grid/flex/minmax where the screen must adapt. |
| LOW | Responsive UX | static\css\operator_dashboard.css:1 | 4 hard-coded widths of 100px+ detected. | Review fixed widths during redesign; prefer grid/flex/minmax where the screen must adapt. |
| LOW | Responsive UX | static\css\page1.css:1 | 12 hard-coded widths of 100px+ detected. | Review fixed widths during redesign; prefer grid/flex/minmax where the screen must adapt. |
| LOW | Responsive UX | static\css\page2.css:1 | 16 hard-coded widths of 100px+ detected. | Review fixed widths during redesign; prefer grid/flex/minmax where the screen must adapt. |
| LOW | Responsive UX | static\css\page3.css:1 | 18 hard-coded widths of 100px+ detected. | Review fixed widths during redesign; prefer grid/flex/minmax where the screen must adapt. |
| LOW | Responsive UX | static\css\page4.css:1 | 5 hard-coded widths of 100px+ detected. | Review fixed widths during redesign; prefer grid/flex/minmax where the screen must adapt. |
| LOW | Responsive UX | static\css\page5.css:1 | 20 hard-coded widths of 100px+ detected. | Review fixed widths during redesign; prefer grid/flex/minmax where the screen must adapt. |
| LOW | Responsive UX | static\css\responsive.css:1 | 4 hard-coded widths of 100px+ detected. | Review fixed widths during redesign; prefer grid/flex/minmax where the screen must adapt. |
| LOW | Responsive UX | static\css\supervisor_dashboard.css:1 | 4 hard-coded widths of 100px+ detected. | Review fixed widths during redesign; prefer grid/flex/minmax where the screen must adapt. |
| LOW | Responsive UX | static\css\user_management.css:1 | 5 hard-coded widths of 100px+ detected. | Review fixed widths during redesign; prefer grid/flex/minmax where the screen must adapt. |

## 14. Recommended Redesign Roadmap

### Phase 1 ? Foundation

- Define colors, typography, spacing, radius and shadows.
- Create shared sidebar/topbar/page-header.
- Standardize buttons, inputs, dropdowns, badges and dialogs.
- Eliminate placeholder-only field identity.

### Phase 2 ? Core Enterprise Patterns

- Standard list/table view.
- Standard search/filter/export toolbar.
- Standard form layout.
- Standard modal/drawer pattern.
- Empty/loading/error states.

### Phase 3 ? MES Priority Pages

Recommended redesign order:

1. Main shell/sidebar.
2. PPC / Job Card creation.
3. Process movement / operator screen.
4. Traceability.
5. Dispatch Tracker.
6. Quality Check.
7. OEE.
8. Analytics.
9. Process Master / Data View.
10. User Management / Admin.

### Phase 4 ? Final UX Hardening

- Keyboard navigation.
- Accessibility labels.
- Responsive behavior.
- Consistent confirmation/error messaging.
- Performance testing on large JC lists.
- Operator usability testing on shop-floor displays.

## 15. Output Files

- `UI_UX_AUDIT_REPORT.md` ? main detailed report.
- `ui_ux_findings.csv` ? actionable issue list.
- `ui_controls_and_placeholders.csv` ? every detected input/select/textarea.
- `ui_ux_audit.json` ? complete machine-readable audit.
