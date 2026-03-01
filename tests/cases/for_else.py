items = [1, 2, 3, 4, 5]
target = 3

for item in items:
    if item == target:
        print(f"Found {target}!")
        break
else:
    print(f"{target} not found in the list.")

# Output: Found 3!

