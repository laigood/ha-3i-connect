"""Constants for the 3irobotix (AllInOne app) integration.

Values marked VERIFIED were confirmed against the live cloud or the APK.
Values marked UNVERIFIED are inferred from strings in libapp.so and must be
checked with real traffic before they can be trusted.
"""

DOMAIN = "threei_robot"

CONF_COUNTRY = "country"
CONF_SIGN_PREFIX = "sign_prefix"
CONF_SIGN_SUFFIX = "sign_suffix"
CONF_TOKEN = "token"
CONF_USER_ID = "user_id"

# VERIFIED: public endpoint, no auth or sign required. Returns host:port per region key.
REGION_URL = "https://cn-appaiot.3irobotix.net/region-service/common/region-server-domains"
DEFAULT_COUNTRY = "CN"

# VERIFIED paths (string literals in libapp.so). The login path answers
# {"code":889,"msg":"签名错误-sign"} when the sign is missing or wrong.
PATH_LOGIN = "/user-center/auth/login"
PATH_DEVICE_LIST = "/device-service/app/bind/listByUserId"

# UNVERIFIED: request field names seen in libapp.so (appKey, timestamp, nonce, sign).
# How they are combined is unknown; see api.build_sign().
SIGN_FIELDS = ("appKey", "timestamp", "nonce")

# VERIFIED: the model string the app uses for this robot.
MODEL_F1_PRO = "sweeperDM2F1Pro"

# VERIFIED topic suffixes (literals in libapp.so). The prefix in front of them
# (product key / device name / "/mqtt/") is UNVERIFIED.
TOPIC_PROPERTY_SET = "thing/service/property/set"
TOPIC_PROPERTY_GET = "thing/service/property/get"
TOPIC_PROPERTY_POST = "thing/event/property/post"
TOPIC_SERVICE_INVOKE = "thing/service_invoke/"
# UNVERIFIED template; {pk}=productKey/productId, {dn}=deviceName/sn.
TOPIC_TEMPLATE = "/sys/{pk}/{dn}/{suffix}"

# VERIFIED service identifiers (literals "service.<name>" in libapp.so).
SERVICE_START_RECHARGE = "start_recharge"
SERVICE_STOP_RECHARGE = "stop_recharge"
SERVICE_GLOBAL_CLEAN = "set_global_clean"
SERVICE_FIND_DEVICE = "find_device"
SERVICE_ROOM_CLEAN = "set_room_clean"

# VERIFIED property identifiers present in libapp.so; their value ranges are UNVERIFIED.
PROP_BATTERY = "quantity"
PROP_WORK_MODE = "work_mode"
PROP_WORK_STATUS = "work_status"
PROP_CHARGE_STATE = "charge_state"
PROP_FAULT = "fault"
PROP_WIND = "wind"
PROP_WATER = "water"
PROP_CLEAN_AREA = "clean_area"
PROP_CLEAN_TIME = "clean_time"
PROP_VOLUME = "volume"
PROP_CHILD_LOCK = "child_lock"
PROP_CARPET_TURBO = "carpet_turbo"
