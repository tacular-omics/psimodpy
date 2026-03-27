import psimodpy


def test_import():
    assert hasattr(psimodpy, "load")
    assert hasattr(psimodpy, "PsiModEntry")
    assert hasattr(psimodpy, "PsiModDatabase")
