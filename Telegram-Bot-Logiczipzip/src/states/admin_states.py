from aiogram.fsm.state import State, StatesGroup


class AdminCategoryStates(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_max_sigs = State()
    waiting_rename = State()
    waiting_new_price = State()
    waiting_new_max_sigs = State()
    waiting_bb_price = State()


class AdminAccountStates(StatesGroup):
    waiting_bulk_data = State()
    waiting_search_phone = State()
    waiting_sig_value = State()
    waiting_sig_used_value = State()
    waiting_priority = State()
    waiting_bulk_limit_category = State()
    waiting_bulk_limit_value = State()
    waiting_reset_account_id = State()
    waiting_mass_priority_value = State()


class AdminTicketStates(StatesGroup):
    waiting_reply = State()
    waiting_search = State()


class AdminBalanceStates(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()


class AdminDepositStates(StatesGroup):
    waiting_amount = State()


class AdminOperatorStates(StatesGroup):
    waiting_id = State()


class AdminUserStates(StatesGroup):
    waiting_search = State()
    waiting_deposit_amount = State()
    waiting_topup_amount = State()
    waiting_totp_limit = State()


class AdminPreorderStates(StatesGroup):
    waiting_message = State()


class AdminBroadcastStates(StatesGroup):
    waiting_message = State()
    waiting_confirm = State()


class AdminPauseStates(StatesGroup):
    waiting_reason = State()


class AdminReputationStates(StatesGroup):
    waiting_name = State()
    waiting_url = State()
    waiting_edit_name = State()
    waiting_edit_url = State()


class AdminFaqStates(StatesGroup):
    waiting_text = State()


class AdminTicketLimitStates(StatesGroup):
    waiting_value = State()


class AdminReviewBonusStates(StatesGroup):
    waiting_value = State()


class AdminStatsStates(StatesGroup):
    waiting_date = State()
    waiting_export_date = State()
    waiting_custom_period = State()
    waiting_admin_stats_date = State()
    waiting_export_phones = State()


class AdminWithdrawDepositStates(StatesGroup):
    waiting_check_link = State()


class AdminMassDeleteStates(StatesGroup):
    waiting_phone_list = State()
    waiting_confirm = State()


class AdminBulkAssignStates(StatesGroup):
    waiting_count = State()


class AdminChannelStates(StatesGroup):
    waiting_channel_id = State()
    waiting_channel_title = State()
    waiting_channel_url = State()


class AdminEnableAccountsStates(StatesGroup):
    waiting_phone_list = State()


class AdminMassEnableStates(StatesGroup):
    waiting_phone_list = State()


class AdminMassDisableStates(StatesGroup):
    waiting_phone_list = State()


class AdminAdminStates(StatesGroup):
    waiting_admin_id = State()


class AdminOrderTotpStates(StatesGroup):
    waiting_totp_amount = State()
    waiting_totp_subtract = State()


class AdminOrderSearchStates(StatesGroup):
    waiting_order_id = State()


class AdminOrderScreenshotStates(StatesGroup):
    waiting_qty = State()
    waiting_screenshot = State()


class AdminReduceSignaturesStates(StatesGroup):
    waiting_count = State()
