struct Foo:
    fn __init__(out self: Foo):
        pass

    fn bar(self: Foo) -> String:
        return "a"


fn main():
    var f = Foo()
    var b = f.bar()
    print(b)
