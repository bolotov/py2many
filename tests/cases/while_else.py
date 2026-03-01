i = 0
while i < 5:
    if i == 10:
        print('This is not supposed to happen.')
        break
    i += 1
else:
    print("The cycle completed without a break.")
