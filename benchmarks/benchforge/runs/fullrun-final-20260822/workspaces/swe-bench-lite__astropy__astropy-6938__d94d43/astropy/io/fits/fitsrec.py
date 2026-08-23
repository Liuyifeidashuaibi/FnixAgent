# Replace exponent separator in floating point numbers
if 'D' in format:
    output_field = output_field.replace(encode_ascii('E'), encode_ascii('D'))
