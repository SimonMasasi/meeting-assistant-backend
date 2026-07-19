import enum 

class UserTypeEnum(str , enum.Enum):
    ADMIN = "ADMIN"
    NORMAL_USER = "NORMAL_USER"
    
    
class FileTypeEnum(str , enum.Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    OTHER = "OTHER"


class UserAuthTokensTypes(str, enum.Enum):
    ACTIVATE_ACCOUNT = "ACTIVATE_ACCOUNT"
    FORGET_PASSWORD = "FORGET_PASSWORD"


class AuthProviderEnum(str, enum.Enum):
    LOCAL = "LOCAL"
    GOOGLE = "GOOGLE"