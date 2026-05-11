import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'lg-labs Infrastructure',
  description: 'Tools base for developers — ELK, Kafka, SonarQube, Grafana, Splunk, Postgres y BackOffice con SSO',
  lang: 'es-ES',
  base: '/infrastructure/',
  lastUpdated: true,
  cleanUrls: true,
  ignoreDeadLinks: [
    /^https?:\/\/localhost(:\d+)?/
  ],

  themeConfig: {
    logo: 'https://pbs.twimg.com/profile_images/1410772782238081029/VO3SPTNV_400x400.jpg',

    nav: [
      { text: 'Inicio', link: '/' },
      { text: 'Guía', link: '/guide/introduction' },
      { text: 'Servicios', link: '/services/' },
      { text: 'BackOffice', link: '/backoffice/' },
      { text: 'Recursos',
        items: [
          { text: 'Repositorio', link: 'https://github.com/lg-labs/infrastructure' },
          { text: 'Blog del autor', link: 'https://lufgarciaqu.medium.com' }
        ]
      }
    ],

    sidebar: {
      '/guide/': [
        {
          text: 'Introducción',
          items: [
            { text: '¿Qué es?', link: '/guide/introduction' },
            { text: 'Requisitos', link: '/guide/requirements' },
            { text: 'Inicio rápido', link: '/guide/quick-start' },
            { text: 'Makefile', link: '/guide/makefile' }
          ]
        }
      ],
      '/services/': [
        {
          text: 'Servicios',
          items: [
            { text: 'Resumen', link: '/services/' },
            { text: 'ELK Stack', link: '/services/elk' },
            { text: 'SonarQube', link: '/services/sonarqube' },
            { text: 'Grafana + Loki', link: '/services/grafana' },
            { text: 'Postgres', link: '/services/postgres' },
            { text: 'Splunk', link: '/services/splunk' },
            { text: 'Kafka', link: '/services/kafka' },
            { text: 'Prometheus', link: '/services/prometheus' }
          ]
        }
      ],
      '/backoffice/': [
        {
          text: 'BackOffice',
          items: [
            { text: 'Resumen', link: '/backoffice/' },
            { text: 'Kafka Dashboard', link: '/backoffice/kafka-dashboard' },
            { text: 'Containers Dashboard', link: '/backoffice/containers-dashboard' }
          ]
        }
      ]
    },

    socialLinks: [
      { icon: 'github', link: 'https://github.com/lg-labs/infrastructure' }
    ],

    footer: {
      message: 'Publicado bajo licencia MIT.',
      copyright: 'Copyright © lg-labs'
    },

    search: {
      provider: 'local'
    },

    editLink: {
      pattern: 'https://github.com/lg-labs/infrastructure/edit/master/docs/:path',
      text: 'Editar esta página en GitHub'
    },

    outline: {
      level: [2, 3],
      label: 'En esta página'
    }
  }
})
