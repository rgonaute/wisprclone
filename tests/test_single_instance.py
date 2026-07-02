from wisprclone.single_instance import SingleInstance, ERROR_ALREADY_EXISTS


def test_first_instance_acquires():
    si = SingleInstance(_create=lambda name: (1234, 0))
    assert si.acquire() is True
    assert si._handle == 1234


def test_second_instance_detected():
    si = SingleInstance(_create=lambda name: (5678, ERROR_ALREADY_EXISTS))
    assert si.acquire() is False


def test_uses_given_name():
    seen = {}
    def create(name):
        seen["name"] = name
        return (1, 0)
    SingleInstance(name="Local\\Foo", _create=create).acquire()
    assert seen["name"] == "Local\\Foo"
