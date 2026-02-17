from aiogram.fsm.state import State, StatesGroup


class TicketStates(StatesGroup):
    waiting_order_select = State()
    waiting_subject = State()
    waiting_message = State()
    waiting_reply = State()
    waiting_general_message = State()
    waiting_deposit_reason = State()
    waiting_attach_choice = State()
    waiting_file = State()
    waiting_file_description = State()


class OrderStates(StatesGroup):
    selecting_category = State()
    confirming_order = State()
    waiting_operator_name = State()
    waiting_quantity = State()
    waiting_preorder_qty = State()
    waiting_preorder_operator = State()
    waiting_custom_qty = State()
    waiting_bb_custom_qty = State()


class PaymentStates(StatesGroup):
    waiting_amount = State()


class ReviewStates(StatesGroup):
    waiting_text = State()


class OperatorStates(StatesGroup):
    waiting_doc_photo = State()
    waiting_doc_photos_batch = State()
