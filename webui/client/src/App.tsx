import { defineComponent, KeepAlive } from 'vue'
import { RouterView, useRouter, useRoute } from 'vue-router'
import {
    NLayout, NLayoutSider, NLayoutContent, NMenu,
    NMessageProvider, NDialogProvider, NConfigProvider,
} from 'naive-ui'
import { zhCN, dateZhCN } from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import { SettingsOutline, PlayCircleOutline, MusicalNotesOutline } from '@vicons/ionicons5'
import { NIcon } from 'naive-ui'
import { h } from 'vue'

function renderIcon(icon: any) {
    return () => h(NIcon, null, { default: () => h(icon) })
}

export default defineComponent({
    name: 'App',
    setup() {
        const router = useRouter()
        const route = useRoute()

        const menuOptions: MenuOption[] = [
            { label: '任务执行', key: '/task', icon: renderIcon(PlayCircleOutline) },
            { label: '音频管理', key: '/audio', icon: renderIcon(MusicalNotesOutline) },
            { label: '配置管理', key: '/config', icon: renderIcon(SettingsOutline) },
        ]

        const handleMenuUpdate = (key: string) => {
            router.push(key)
        }

        return () => (
            <NConfigProvider locale={zhCN} dateLocale={dateZhCN}>
                <NMessageProvider>
                    <NDialogProvider>
                        <NLayout has-sider style="height: 100vh">
                            <NLayoutSider
                                bordered
                                width={200}
                                collapsed-width={64}
                                show-trigger
                                collapse-mode="width"
                                style="background: #fff"
                            >
                                <div style="padding: 16px; text-align: center; font-weight: bold; font-size: 14px; border-bottom: 1px solid #efeff5">
                                    音频切分工具
                                </div>
                                <NMenu
                                    options={menuOptions}
                                    value={route.path}
                                    onUpdateValue={handleMenuUpdate}
                                />
                            </NLayoutSider>
                            <NLayoutContent style="padding: 16px; background: #f5f5f5; overflow: hidden;">
                                <RouterView v-slots={{
                                    default: ({ Component }: any) => (
                                        <KeepAlive>
                                            {Component ? h(Component) : null}
                                        </KeepAlive>
                                    ),
                                }} />
                            </NLayoutContent>
                        </NLayout>
                    </NDialogProvider>
                </NMessageProvider>
            </NConfigProvider>
        )
    },
})
