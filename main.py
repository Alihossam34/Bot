import requests
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler

# تفعيل التسجيل (logging) لرؤية الأخطاء والرسائل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================================================================
# معلومات البوت والقناة (تم تحديث BOT_TOKEN)
# ==============================================================================
BOT_TOKEN = "7837846876:AAEGf1j6U9YIHoSNmuf48aa_iI9uAr3ob3k" # <--- تم وضع التوكن الخاص بك هنا!
CHANNEL_USERNAME = "IDGAWI" # اسم المستخدم للقناة بدون @
CHANNEL_ID = -1002703124705 # معرف القناة الرقمي (مهم للتحقق من الاشتراك)

# ==============================================================================
# تعريف حالات المحادثة
# ==============================================================================
START_STATE, CHECK_SUBSCRIPTION, NUMBER, PASSWORD, SELECT_PACKAGE = range(5) # تم إضافة START_STATE و CHECK_SUBSCRIPTION

# ==============================================================================
# دالة التفاعل مع Vodafone API (معدلة لعرض الأسماء العربية)
# ==============================================================================
def vodafone_api_interaction(number, password, target_subscription=None):
    """
    تتفاعل مع Vodafone API للمصادقة، الحصول على المنتجات المؤهلة،
    واختياريًا تفعيل باقة معينة.

    Args:
        number (str): رقم فودافون الخاص بالمستخدم.
        password (str): كلمة مرور فودافون الخاصة بالمستخدم.
        target_subscription (str, optional): معرف الباقة التقني (TechnicalID) المراد تفعيلها.
                                             إذا كان None، يتم إرجاع الباقات المؤهلة فقط.

    Returns:
        dict: قاموس يحتوي على الحالة والبيانات.
              - 'status': 'success' أو 'failure'
              - 'message': وصف للنتيجة.
              - 'data': بيانات ذات صلة مثل الباقات المؤهلة (قائمة من القواميس) أو استجابة التفعيل.
    """
    # --- المصادقة ---
    auth_url = "https://mobile.vodafone.com.eg/auth/realms/vf-realm/protocol/openid-connect/token"
    auth_payload = {
        'grant_type': "password",
        'username': number,
        'password': password,
        'client_secret': "a2ec6fff-0b7f-4aa4-a733-96ceae5c84c3",
        'client_id': "my-vodafone-app"
    }
    auth_headers = {
        'User-Agent': "okhttp/4.9.3",
        'Accept': "application/json, text/plain, */*",
        'Accept-Encoding': "gzip",
        'Content-Type': "application/x-www-form-urlencoded",
        'x-dynatrace': "MT_3_5_4182424370_1_a556db1b-4506-43f3-854a-1d2527767923_0_761_178",
        'x-agent-operatingsystem': "A055FXXS8CXL2",
        'clientId': "xxx",
        'x-agent-device': "a05m",
        'x-agent-version': "2024.10.1",
        'x-agent-build': "562"
    }

    try:
        auth_response = requests.post(auth_url, data=auth_payload, headers=auth_headers, timeout=10)
        auth_response.raise_for_status() # يرفع HTTPError للاستجابات السيئة (4xx أو 5xx)
        tok = auth_response.json()['access_token']
        logger.info("Authentication successful.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Authentication failed (connection error): {e}")
        return {'status': 'failure', 'message': f"فشل المصادقة (خطأ في الاتصال): {e}"}
    except KeyError:
        logger.error(f"Authentication failed (invalid credentials/response): {auth_response.text}")
        return {'status': 'failure', 'message': f"فشل المصادقة (بيانات غير صحيحة أو استجابة غير متوقعة): {auth_response.text}"}
    except json.JSONDecodeError:
        logger.error(f"Authentication failed (invalid JSON response): {auth_response.text}")
        return {'status': 'failure', 'message': f"فشل المصادقة (استجابة غير صالحة): {auth_response.text}"}

    # --- الحصول على عروض المنتجات المؤهلة ---
    epo_url = "https://mobile.vodafone.com.eg/services/dxl/epo/eligibleProductOffering"
    epo_params = {
        'customerAccountId': number,
        'type': "MIProducts",
        'subscriptionId': "MI_BASIC_SUPER_10" # قد تحتاج لتغيير هذا إذا كان يؤثر على الباقات المعروضة
    }
    epo_headers = {
        'User-Agent': "okhttp/4.11.0",
        'Connection': "Keep-Alive",
        'Accept': "application/json",
        'Accept-Encoding': "gzip",
        'api-host': "EligibleProductOfferingHost",
        'useCase': "MIProfile",
        'Authorization': f"Bearer {tok}",
        'api-version': "v2",
        'x-agent-operatingsystem': "14",
        'clientId': "AnaVodafoneAndroid",
        'x-agent-device': "Samsung SM-A055F",
        'x-agent-version': "2024.12.1",
        'x-agent-build': "946",
        'Content-Type': "application/json",
        'msisdn': number,
        'Accept-Language': "ar" # طلب المحتوى العربي
    }

    try:
        epo_response = requests.get(epo_url, params=epo_params, headers=epo_headers, timeout=10)
        epo_response.raise_for_status()
        response_data = epo_response.json()
        logger.info("Successfully retrieved eligible product offerings.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get eligible packages (connection error): {e}")
        return {'status': 'failure', 'message': f"فشل الحصول على الباقات المتاحة (خطأ في الاتصال): {e}"}
    except json.JSONDecodeError:
        logger.error(f"Failed to get eligible packages (invalid JSON response): {epo_response.text}")
        return {'status': 'failure', 'message': f"فشل الحصول على الباقات المتاحة (استجابة غير صالحة): {epo_response.text}"}

    eligible_packages_list = []
    for item in response_data:
        if 'parts' in item and 'productOffering' in item['parts']:
            for offering in item['parts']['productOffering']:
                tech_id = None
                enc_prod_id = None
                display_name = None

                # محاولة استخراج اسم العرض من حقول مختلفة
                if 'name' in offering:
                    display_name = offering['name']
                elif 'description' in offering:
                    display_name = offering['description']
                # يمكنك إضافة المزيد من الحقول هنا بناءً على استجابة الـ API الفعلية
                # مثال: elif 'localizedName' in offering: display_name = offering['localizedName']

                if 'id' in offering:
                    for id_item in offering['id']:
                        if id_item.get('schemeName') == 'TechnicalID':
                            tech_id = id_item.get('value')
                        if id_item.get('schemeName') == 'EncProductID':
                            enc_prod_id = id_item.get('value')
                    
                    if tech_id and enc_prod_id:
                        if not display_name:
                            display_name = tech_id # fallback to tech_id if no display name found
                        
                        eligible_packages_list.append({
                            'tech_id': tech_id,
                            'enc_prod_id': enc_prod_id,
                            'display_name': display_name
                        })

    if not eligible_packages_list:
        return {'status': 'failure', 'message': "لم يتم العثور على باقات متاحة لحسابك."}

    if target_subscription:
        # البحث عن encProductId للباقة المستهدفة من القائمة الجديدة
        selected_package_info = next((p for p in eligible_packages_list if p['tech_id'] == target_subscription), None)
        if not selected_package_info:
            return {'status': 'failure', 'message': f"الباقة المطلوبة '{target_subscription}' غير متاحة أو غير مؤهلة لحسابك."}
        encProductId = selected_package_info['enc_prod_id']

        # --- تفعيل الباقة ---
        po_url = "https://mobile.vodafone.com.eg/services/dxl/pom/productOrder"
        po_payload = {
            "channel": {"name": "MobileApp"},
            "orderItem": [{
                "action": "add",
                "product": {
                    "characteristic": [
                        {"name": "LangId", "value": "ar"},
                        {"name": "ExecutionType", "value": "Sync"},
                        {"name": "DropAddons", "value": "False"},
                        {"name": "MigrationType", "value": "Downgrade"},
                        {"name": "OneStepMigrationFlag", "value": "Y"},
                        {"name": "Journey", "value": "MI_ELigibility"}
                    ],
                    "encProductId": encProductId,
                    "id": target_subscription,
                    "relatedParty": [{"id": number, "name": "MSISDN", "role": "Subscriber"}],
                    "@type": "MI"
                },
                "eCode": 0
            }],
            "@type": "MIProfile"
        }
        po_headers = {
            'User-Agent': "okhttp/4.11.0",
            'Connection': "Keep-Alive",
            'Accept': "application/json",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/json; charset=UTF-8",
            'api-host': "ProductOrderingManagement",
            'useCase': "MIProfile",
            'Authorization': f"Bearer {tok}",
            'api-version': "v2",
            'x-agent-operatingsystem': "14",
            'clientId': "AnaVodafoneAndroid",
            'x-agent-device': "Samsung SM-A055F",
            'x-agent-version': "2024.12.1",
            'x-agent-build': "946",
            'msisdn': number,
            'Accept-Language': "ar"
        }

        try:
            po_response = requests.post(po_url, data=json.dumps(po_payload), headers=po_headers, timeout=10)
            po_response.raise_for_status()
            logger.info(f"Package activation request sent for {target_subscription}.")
            return {'status': 'success', 'message': "تم إرسال طلب تفعيل الباقة بنجاح.", 'data': po_response.json()}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to activate package (connection error): {e}")
            return {'status': 'failure', 'message': f"فشل تفعيل الباقة (خطأ في الاتصال): {e}"}
        except json.JSONDecodeError:
            logger.error(f"Failed to activate package (invalid JSON response): {po_response.text}")
            return {'status': 'failure', 'message': f"فشل تفعيل الباقة (استجابة غير صالحة): {po_response.text}"}
    else:
        return {'status': 'success', 'message': "تم الحصول على الباقات المتاحة بنجاح.", 'data': eligible_packages_list}

# ==============================================================================
# دوال بوت تيليجرام
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يبدأ المحادثة ويعرض معلومات المنشئ والقناة ويطلب الاشتراك."""
    creator_info = "منشئ البوت: Idjawi\nاليوزر الخاص بي في التليجرام: @Alihossam190"
    channel_link = f"https://t.me/{CHANNEL_USERNAME}"

    welcome_message = (
        f"مرحباً بك في بوت فودافون لتفعيل الباقات!\n\n"
        f"{creator_info}\n\n"
        f"للاستفادة من خدمات البوت، يرجى الانضمام إلى قناتنا على تيليجرام:\n"
        f"{channel_link}\n\n"
        f"بعد الانضمام، اضغط على الزر أدناه للمتابعة."
    )

    keyboard = [[InlineKeyboardButton("لقد انضممت إلى القناة", callback_data="check_channel_subscription")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome_message, reply_markup=reply_markup)
    return CHECK_SUBSCRIPTION # الانتقال إلى حالة التحقق من الاشتراك

async def check_subscription_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يتحقق من اشتراك المستخدم في القناة."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    try:
        chat_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        # التحقق مما إذا كان المستخدم عضواً، مسؤولاً، أو منشئاً
        if chat_member.status in ['member', 'administrator', 'creator']:
            await query.edit_message_text("أهلاً بك! تم التحقق من عضويتك بنجاح.\nالآن، يرجى إدخال رقم فودافون الخاص بك (مثال: 01012345678):")
            return NUMBER # المتابعة لطلب الرقم
        else:
            # المستخدم مقيد، غادر، أو تم طرده
            keyboard = [[InlineKeyboardButton("لقد انضممت إلى القناة", callback_data="check_channel_subscription")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "لم يتم التحقق من عضويتك بعد. يرجى الانضمام أولاً إلى القناة "
                f"@{CHANNEL_USERNAME} ثم اضغط على الزر مرة أخرى.",
                reply_markup=reply_markup
            )
            return CHECK_SUBSCRIPTION # البقاء في هذه الحالة
    except Exception as e:
        logger.error(f"Error checking channel subscription for user {user_id}: {e}")
        keyboard = [[InlineKeyboardButton("لقد انضممت إلى القناة", callback_data="check_channel_subscription")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "حدث خطأ أثناء التحقق من عضويتك. يرجى التأكد من أن البوت مسؤول في القناة "
            f"@{CHANNEL_USERNAME} ثم اضغط على الزر مرة أخرى."
            "\n\nملاحظة: قد تحتاج إلى إعادة تشغيل البوت أو المحاولة لاحقًا إذا استمر الخطأ."
            , reply_markup=reply_markup
        )
        return CHECK_SUBSCRIPTION # البقاء في هذه الحالة

async def get_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يتلقى رقم فودافون ويطلب كلمة المرور."""
    # هذه الدالة يتم الوصول إليها بعد التحقق من اشتراك القناة
    user_number = update.message.text
    if not user_number.isdigit() or len(user_number) != 11: # تحقق بسيط من الرقم
        await update.message.reply_text("الرقم غير صحيح. يرجى إدخال رقم فودافون مكون من 11 رقمًا فقط.")
        return NUMBER
    
    context.user_data['number'] = user_number
    await update.message.reply_text("الآن، يرجى إدخال كلمة مرور حساب فودافون الخاص بك:")
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يتلقى كلمة المرور ويحاول المصادقة وجلب الباقات."""
    user_password = update.message.text
    context.user_data['password'] = user_password
    user_number = context.user_data['number']

    await update.message.reply_text("جاري التحقق من بياناتك وجلب الباقات المتاحة، يرجى الانتظار...")

    # استدعاء دالة التفاعل مع Vodafone API
    result = vodafone_api_interaction(user_number, user_password)

    if result['status'] == 'success':
        available_packages = result['data'] # هذه الآن قائمة من القواميس
        if available_packages:
            keyboard = []
            # تخزين الباقات في user_data لاستخدامها لاحقًا في callback_query
            # نستخدم قاموس هنا لتسهيل البحث عن الباقة بمعرفها التقني (tech_id)
            context.user_data['available_packages_info'] = {p['tech_id']: p for p in available_packages}

            for package_info in available_packages:
                # callback_data يجب أن يكون سلسلة نصية
                # نستخدم display_name لزر الباقة و tech_id في الـ callback_data
                keyboard.append([InlineKeyboardButton(package_info['display_name'], callback_data=f"select_package_{package_info['tech_id']}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "يرجى اختيار الباقة التي ترغب في تفعيلها:",
                reply_markup=reply_markup
            )
            return SELECT_PACKAGE
        else:
            await update.message.reply_text("عذراً، لم يتم العثور على أي باقات متاحة لحسابك.")
            return ConversationHandler.END
    else:
        await update.message.reply_text(f"❌ فشل المصادقة أو جلب الباقات: {result['message']}\nيرجى المحاولة مرة أخرى أو التأكد من صحة بياناتك.")
        return ConversationHandler.END

async def select_package(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يتعامل مع اختيار المستخدم للباقة."""
    query = update.callback_query
    await query.answer() # يجب استدعاء answer() لكل callback_query

    selected_tech_id = query.data.replace("select_package_", "")
    
    user_number = context.user_data['number']
    user_password = context.user_data['password']
    
    # الحصول على اسم العرض للباقة المختارة من البيانات المخزنة
    package_info = context.user_data['available_packages_info'].get(selected_tech_id)
    display_name = package_info['display_name'] if package_info else selected_tech_id # استخدم display_name أو tech_id كخيار احتياطي

    await query.edit_message_text(f"جاري محاولة تفعيل باقة: {display_name}، يرجى الانتظار...")

    # استدعاء دالة التفاعل مع Vodafone API لتفعيل الباقة
    result = vodafone_api_interaction(user_number, user_password, target_subscription=selected_tech_id)

    if result['status'] == 'success':
        await query.edit_message_text(
            f"✅ الف مبروك تم تفعيل العرض الباقة {display_name} بنجاح بواسطه Idejaw" # رسالة التفعيل النهائية
        )
    else:
        await query.edit_message_text(
            f"❌ فشل تفعيل باقة {display_name}: {result['message']}\nيرجى المحاولة مرة أخرى."
        )
    
    # إنهاء المحادثة بعد التفعيل أو الفشل
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """يلغي المحادثة."""
    await update.message.reply_text(
        "تم إلغاء العملية. يمكنك البدء مرة أخرى باستخدام /start."
    )
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يسجل الأخطاء التي تسببها التحديثات."""
    logger.error(f"Update {update} caused error {context.error}")
    if update.effective_message:
        await update.effective_message.reply_text(
            "حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى باستخدام /start."
        )

# ==============================================================================
# إعداد وتشغيل البوت
# ==============================================================================
def main() -> None:
    """يشغل البوت."""
    application = Application.builder().token(BOT_TOKEN).build()

    # تعريف ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHECK_SUBSCRIPTION: [CallbackQueryHandler(check_subscription_status, pattern="^check_channel_subscription$")],
            NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_number)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            SELECT_PACKAGE: [CallbackQueryHandler(select_package, pattern=r'^select_package_')],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)

    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
    
