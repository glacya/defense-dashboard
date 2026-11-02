from types import SimpleNamespace

from dashboard import router


def test_page_renderer_imports_module_only_when_called(monkeypatch):
    imports = []
    rendered = []
    monkeypatch.setattr(
        router,
        'import_module',
        lambda module_name: imports.append(module_name) or SimpleNamespace(
            render=lambda: rendered.append(module_name)
        ),
    )

    render_page = router._page_renderer('dashboard.views.example')

    assert imports == []
    assert rendered == []

    render_page()

    assert imports == ['dashboard.views.example']
    assert rendered == ['dashboard.views.example']
