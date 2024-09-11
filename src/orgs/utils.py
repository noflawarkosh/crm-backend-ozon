import random
import string


def generate_invitation_code():
    random_string = ''
    for i in range(11):
        if i == 3 or i == 7:
            random_string += '-'
        else:
            random_string += random.choice(string.ascii_letters + string.digits)

    return random_string.upper()
