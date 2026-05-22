import enum 

class UserTypeEnum(str , enum.Enum):
    ADMIN = "ADMIN"
    NORMAL_USER = "NORMAL_USER"